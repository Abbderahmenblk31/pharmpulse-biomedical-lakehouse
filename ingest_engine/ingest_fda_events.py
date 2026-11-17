"""
PharmPulse - Biomedical Adverse Drug Event Ingestion Engine
===========================================================
Ingests 100% genuine post-marketing adverse drug event reports from the
official US Food and Drug Administration (OpenFDA API: drug/event.json).
Unnests deeply nested clinical JSON payloads (Patients, Suspect Drugs,
and MedDRA coded adverse reactions). Persists records into DuckDB.
"""

import os
import sys
import re
import time
import requests
import duckdb
import pandas as pd
from datetime import datetime, timezone

# Ensure stdout handles UTF-8 on Windows consoles
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKEHOUSE_DIR = os.path.join(BASE_DIR, "data", "lakehouse")
os.makedirs(LAKEHOUSE_DIR, exist_ok=True)
DB_PATH = os.path.join(LAKEHOUSE_DIR, "biomedical_lakehouse.duckdb")

OPENFDA_URL = "https://api.fda.gov/drug/event.json"
HEADERS = {"User-Agent": "PharmPulse-Biomedical-Lakehouse/1.0 (Public-Health-Research)"}

def clean_drug_name(raw_name):
    """Normalizes raw pharmaceutical product brand/generic names."""
    if not raw_name:
        return "UNKNOWN"
    name = str(raw_name).strip().upper()
    # Remove dosage strengths like 100MG, 10MG, 50 MCG, 0.5ML, etc.
    name = re.sub(r'\b\d+(\.\d+)?\s*(MG|MCG|G|ML|%|IU|UNIT)\b', '', name)
    # Remove dosage form descriptions like TABLET, CAPSULE, INJECTION, SOLUTION, PATCH, XR, ER
    name = re.sub(r'\b(TABLET|TABLETS|CAPSULE|CAPSULES|INJECTION|SOLUTION|SUSPENSION|PATCH|CREAM|OINTMENT|ORAL|XR|ER|SR|HCL)\b', '', name)
    # Remove trailing non-alphanumeric punctuation
    name = re.sub(r'[\(\)\[\]\/\-\,\.]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name if len(name) >= 2 else "UNKNOWN"

def fetch_fda_adverse_events(target_reports=300, batch_size=100):
    """
    Queries OpenFDA API across diverse clinical queries to collect
    both common and life-threatening adverse reaction profiles.
    """
    print(f"[1/3] Querying OpenFDA API for clinical adverse event reports...")
    
    # Query slices for clinical diversity
    queries = [
        {"search": "serious:1", "desc": "Serious/Hospitalized Events"},
        {"search": "patient.drug.drugcharacterization:1", "desc": "Primary Suspect Drug Cases"},
        {"search": "seriousnessdeath:1", "desc": "Fatal Toxicity Outcomes"}
    ]
    
    raw_reports = []
    seen_report_ids = set()
    
    for q in queries:
        print(f"   -> Fetching slice: {q['desc']} (Query: '{q['search']}')")
        skip = 0
        while len(raw_reports) < target_reports:
            url = f"{OPENFDA_URL}?search={q['search']}&limit={batch_size}&skip={skip}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code != 200:
                    print(f"      [!] API returned status {resp.status_code} at skip={skip}, ending slice.")
                    break
                    
                results = resp.json().get("results", [])
                if not results:
                    break
                    
                added_count = 0
                for r in results:
                    rep_id = str(r.get("safetyreportid") or "").strip()
                    if not rep_id or rep_id in seen_report_ids:
                        continue
                        
                    seen_report_ids.add(rep_id)
                    raw_reports.append(r)
                    added_count += 1
                    
                print(f"      • Skip {skip}: Added {added_count} reports (Cumulative: {len(raw_reports)}/{target_reports})")
                skip += batch_size
                time.sleep(0.3) # Respect OpenFDA rate limits
                
                if added_count == 0 or len(raw_reports) >= target_reports:
                    break
                    
            except Exception as e:
                print(f"      [!] Network error at skip={skip}: {e}")
                break
                
    print(f"\n[2/3] Parsing & unnesting {len(raw_reports):,} clinical report hierarchies...")
    
    reports_data = []
    pairs_data = []
    
    for r in raw_reports:
        rep_id = str(r.get("safetyreportid") or "").strip()
        receive_date = str(r.get("receiptdate") or r.get("receivedate") or "")[:8]
        
        # Patient demographics
        patient = r.get("patient", {})
        age = patient.get("patientonsetage")
        sex_code = patient.get("patientsex", 0) # 1: Male, 2: Female, 0: Unknown
        
        # Clinical outcomes
        is_serious = 1 if str(r.get("serious")) == "1" else 0
        is_death = 1 if str(r.get("seriousnessdeath")) == "1" else 0
        is_hosp = 1 if str(r.get("seriousnesshospitalization")) == "1" else 0
        is_life_threat = 1 if str(r.get("seriousnesslifethreatening")) == "1" else 0
        is_disabling = 1 if str(r.get("seriousnessdisabling")) == "1" else 0
        
        reports_data.append({
            "report_id": rep_id,
            "receive_date": receive_date,
            "patient_age": float(age) if age is not None and str(age).replace('.', '', 1).isdigit() else None,
            "patient_sex": "Male" if sex_code == 1 else "Female" if sex_code == 2 else "Unknown",
            "is_serious": is_serious,
            "is_fatal": is_death,
            "is_hospitalized": is_hosp,
            "is_life_threatening": is_life_threat,
            "is_disabling": is_disabling,
            "ingested_at_utc": datetime.now(timezone.utc)
        })
        
        # Extract suspect and concomitant drugs
        drugs = patient.get("drug", [])
        reactions = patient.get("reaction", [])
        
        extracted_drugs = set()
        for d in drugs:
            raw_prod = d.get("medicinalproduct")
            cleaned_prod = clean_drug_name(raw_prod)
            char_role = d.get("drugcharacterization", "1")
            # We track all identified drugs, noting suspect vs concomitant
            if cleaned_prod != "UNKNOWN":
                extracted_drugs.add((cleaned_prod, str(char_role)))
                
        extracted_reactions = set()
        for rx in reactions:
            meddra_term = str(rx.get("reactionmeddrapt") or "").strip().upper()
            if meddra_term:
                extracted_reactions.add(meddra_term)
                
        # Generate granular Drug-Reaction contingency pairs
        for drug_name, char_role in extracted_drugs:
            for reaction_term in extracted_reactions:
                pairs_data.append({
                    "report_id": rep_id,
                    "drug_name": drug_name,
                    "is_suspect_drug": 1 if char_role == "1" else 0,
                    "adverse_reaction": reaction_term,
                    "is_fatal": is_death,
                    "is_hospitalized": is_hosp
                })
                
    df_reports = pd.DataFrame(reports_data)
    df_pairs = pd.DataFrame(pairs_data)
    
    print(f"   -> Successfully extracted {len(df_reports):,} patient reports.")
    print(f"   -> Successfully unnested {len(df_pairs):,} drug-adverse reaction pairs.")
    return df_reports, df_pairs

def persist_to_lakehouse(df_reports, df_pairs):
    """Saves clinical reports and unnested pairs into DuckDB Lakehouse Bronze layer."""
    print("[3/3] Ingesting biomedical records into DuckDB Lakehouse...")
    con = duckdb.connect(DB_PATH)
    
    con.register("df_reports", df_reports)
    con.register("df_pairs", df_pairs)
    
    con.execute("""
        CREATE OR REPLACE TABLE raw_clinical_reports AS
        SELECT * FROM df_reports;
    """)
    
    con.execute("""
        CREATE OR REPLACE TABLE raw_drug_reaction_pairs AS
        SELECT * FROM df_pairs;
    """)
    
    stats = con.execute("""
        SELECT 
            COUNT(DISTINCT r.report_id) as total_reports,
            COUNT(DISTINCT p.drug_name) as unique_drugs,
            COUNT(DISTINCT p.adverse_reaction) as unique_reactions,
            SUM(r.is_fatal) as total_fatalities,
            SUM(r.is_hospitalized) as total_hospitalizations
        FROM raw_clinical_reports r
        LEFT JOIN raw_drug_reaction_pairs p ON r.report_id = p.report_id;
    """).fetchone()
    
    print("\n" + "="*70)
    print("SUCCESS: PHARMPULSE BIOMEDICAL LAKEHOUSE INGESTION COMPLETE!")
    print(f"   * Lakehouse Database: {DB_PATH}")
    print(f"   * Total Clinical Reports:      {stats[0]:,}")
    print(f"   * Unique Pharmaceutical Drugs: {stats[1]:,}")
    print(f"   * Unique MedDRA Reactions:     {stats[2]:,}")
    print(f"   * Documented Fatal Cases:      {stats[3]:,}")
    print(f"   * Hospitalized Patients:       {stats[4]:,}")
    print("="*70 + "\n")
    con.close()

if __name__ == "__main__":
    print("="*70)
    print("  PHARMPULSE: OPENFDA ADVERSE DRUG EVENTS INGESTION ENGINE")
    print("="*70)
    df_rep, df_pr = fetch_fda_adverse_events(target_reports=300, batch_size=100)
    persist_to_lakehouse(df_rep, df_pr)
