"""
PharmPulse - Epidemiological Signal Detection & Pharmacovigilance Engine
========================================================================
Implements FDA & WHO international standards for pharmacovigilance:
1. 2x2 Disproportionality Contingency Matrix (a, b, c, d).
2. Proportional Reporting Ratio (PRR) algorithm.
3. Reporting Odds Ratio (ROR) with 95% Confidence Intervals.
4. Black-Box Warning Candidate Classification & Fatality Risk Scoring.
"""

import os
import sys
import math
import duckdb
import pandas as pd

if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "lakehouse", "biomedical_lakehouse.duckdb")

def run_epidemiology_models():
    print("="*75)
    print("  PHARMPULSE: EPIDEMIOLOGICAL SIGNAL DETECTION & SAFETY ENGINE")
    print("="*75)
    
    con = duckdb.connect(DB_PATH)
    
    # 1. Silver Layer: Cleaned Drug-Reaction Observations
    print("[1/4] Engineering Silver Layer: Standardizing drug-event pairs...")
    con.execute("""
        CREATE OR REPLACE TABLE silver_drug_safety_pairs AS
        SELECT 
            report_id,
            drug_name,
            adverse_reaction,
            is_suspect_drug,
            is_fatal,
            is_hospitalized
        FROM raw_drug_reaction_pairs
        WHERE drug_name != 'UNKNOWN' 
          AND adverse_reaction IS NOT NULL 
          AND adverse_reaction != '';
    """)
    print("   -> Standardized clinical observations into relational silver mart.")
    
    # 2. Gold Mart 1: Construct 2x2 Contingency Table for PRR & ROR
    print("[2/4] Constructing 2x2 Contingency Matrix (a, b, c, d) in pure SQL...")
    
    con.execute("""
        CREATE OR REPLACE TABLE mart_fda_safety_signals AS
        WITH total_events AS (
            SELECT COUNT(*) as grand_total FROM silver_drug_safety_pairs
        ),
        drug_totals AS (
            SELECT drug_name, COUNT(*) as total_drug_events
            FROM silver_drug_safety_pairs
            GROUP BY drug_name
        ),
        reaction_totals AS (
            SELECT adverse_reaction, COUNT(*) as total_reaction_events
            FROM silver_drug_safety_pairs
            GROUP BY adverse_reaction
        ),
        pair_counts AS (
            SELECT 
                drug_name,
                adverse_reaction,
                COUNT(*) as a_count,
                SUM(is_fatal) as fatal_count,
                SUM(is_hospitalized) as hosp_count
            FROM silver_drug_safety_pairs
            GROUP BY drug_name, adverse_reaction
            HAVING COUNT(*) >= 2 -- Filter singletons to ensure statistical significance
        )
        SELECT 
            p.drug_name,
            p.adverse_reaction,
            p.a_count as a, -- Target drug with Target reaction
            (dt.total_drug_events - p.a_count) as b, -- Target drug with OTHER reactions
            (rt.total_reaction_events - p.a_count) as c, -- OTHER drugs with Target reaction
            (te.grand_total - dt.total_drug_events - rt.total_reaction_events + p.a_count) as d, -- OTHER drugs with OTHER reactions
            p.fatal_count,
            p.hosp_count,
            -- Proportional Reporting Ratio (PRR): [a / (a + b)] / [c / (c + d)]
            ROUND(
                (CAST(p.a_count AS DOUBLE) / NULLIF(dt.total_drug_events, 0)) / 
                NULLIF((CAST(rt.total_reaction_events - p.a_count AS DOUBLE) / NULLIF(te.grand_total - dt.total_drug_events, 0)), 0),
                2
            ) as prr,
            -- Reporting Odds Ratio (ROR): (a * d) / (b * c)
            ROUND(
                (CAST(p.a_count AS DOUBLE) * (te.grand_total - dt.total_drug_events - rt.total_reaction_events + p.a_count)) /
                NULLIF(CAST(dt.total_drug_events - p.a_count AS DOUBLE) * (rt.total_reaction_events - p.a_count), 0),
                2
            ) as ror,
            -- Log Standard Error for ROR: sqrt(1/a + 1/b + 1/c + 1/d)
            SQRT(
                (1.0 / NULLIF(p.a_count, 0)) + 
                (1.0 / NULLIF(dt.total_drug_events - p.a_count, 0)) + 
                (1.0 / NULLIF(rt.total_reaction_events - p.a_count, 0)) + 
                (1.0 / NULLIF(te.grand_total - dt.total_drug_events - rt.total_reaction_events + p.a_count, 0))
            ) as ror_se
        FROM pair_counts p
        JOIN drug_totals dt ON p.drug_name = dt.drug_name
        JOIN reaction_totals rt ON p.adverse_reaction = rt.adverse_reaction
        CROSS JOIN total_events te
        WHERE (dt.total_drug_events - p.a_count) > 0 
          AND (rt.total_reaction_events - p.a_count) > 0;
    """)
    
    # 3. Gold Mart 1.1: Calculate 95% Confidence Intervals & Flag Black Box Signals
    print("[3/4] Calculating 95% Confidence Intervals & FDA Signal Classification...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_fda_safety_signals AS
        SELECT 
            drug_name,
            adverse_reaction,
            a as report_count,
            fatal_count,
            hosp_count,
            prr,
            ror,
            ROUND(EXP(LN(NULLIF(ror, 0)) - 1.96 * ror_se), 2) as ror_ci_lower,
            ROUND(EXP(LN(NULLIF(ror, 0)) + 1.96 * ror_se), 2) as ror_ci_upper,
            -- Official FDA Pharmacovigilance Signal Definition:
            -- PRR >= 2.0 AND ROR Lower CI > 1.0 AND report count a >= 3
            CASE 
                WHEN prr >= 2.0 AND EXP(LN(NULLIF(ror, 0)) - 1.96 * ror_se) > 1.0 AND a >= 3 
                THEN 'FDA POTENTIAL SAFETY SIGNAL (HIGH RISK)'
                WHEN prr >= 2.0 AND a >= 2 
                THEN 'EMERGING SIGNAL (ELEVATED PRR)'
                ELSE 'MONITORED BASELINE'
            END as fda_signal_status
        FROM mart_fda_safety_signals
        ORDER BY prr DESC, report_count DESC;
    """)
    
    # 4. Gold Mart 2: Drug Fatality & Toxicity Severity Profiler
    print("[4/4] Generating Drug Fatality & Clinical Outcome Risk Matrix...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_drug_fatality_risk AS
        SELECT 
            drug_name,
            COUNT(DISTINCT report_id) as total_patient_cases,
            SUM(is_fatal) as fatal_events,
            SUM(is_hospitalized) as hospitalizations,
            ROUND(SUM(is_fatal) * 100.0 / NULLIF(COUNT(DISTINCT report_id), 0), 1) as fatality_rate_pct,
            ROUND(SUM(is_hospitalized) * 100.0 / NULLIF(COUNT(DISTINCT report_id), 0), 1) as hospitalization_rate_pct
        FROM silver_drug_safety_pairs
        GROUP BY drug_name
        HAVING COUNT(DISTINCT report_id) >= 3
        ORDER BY fatal_events DESC, fatality_rate_pct DESC;
    """)
    
    # 5. Gold Mart 3: Prescriptive Regulatory & Clinical Action Engine
    print("[5/5] Generating Prescriptive Regulatory & Clinical Action Engine...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_prescriptive_regulatory_actions AS
        WITH signal_scored AS (
            SELECT 
                s.drug_name,
                s.adverse_reaction,
                s.report_count,
                s.fatal_count,
                s.hosp_count,
                s.prr,
                s.ror,
                s.ror_ci_lower,
                s.ror_ci_upper,
                s.fda_signal_status,
                ROUND((s.fatal_count * 100.0) / NULLIF(s.report_count, 0), 1) as pair_fatality_pct,
                ROUND((s.hosp_count * 100.0) / NULLIF(s.report_count, 0), 1) as pair_hosp_pct,
                -- Composite Clinical Risk Score (0-100)
                ROUND(
                    LEAST(40.0, (s.prr * 6.0) + (s.ror_ci_lower * 4.0)) +
                    LEAST(35.0, ((s.fatal_count * 100.0) / NULLIF(s.report_count, 0)) * 0.35 + (s.fatal_count * 10.0)) +
                    LEAST(25.0, ((s.hosp_count * 100.0) / NULLIF(s.report_count, 0)) * 0.25),
                    1
                ) as clinical_risk_score
            FROM mart_fda_safety_signals s
            WHERE s.report_count >= 2
        )
        SELECT 
            drug_name,
            adverse_reaction,
            report_count,
            fatal_count,
            hosp_count,
            prr,
            ror,
            ror_ci_lower,
            ror_ci_upper,
            pair_fatality_pct,
            pair_hosp_pct,
            clinical_risk_score,
            CASE 
                WHEN clinical_risk_score >= 65 OR (prr >= 2.5 AND fatal_count >= 1) THEN '🚨 TIER 1: MANDATORY BLACK-BOX WARNING & REMS'
                WHEN clinical_risk_score >= 40 OR (prr >= 2.0 AND hosp_count >= 2) THEN '⚠️ TIER 2: CONTRAINDICATION RESTRICTION & LABEL REVISION'
                WHEN clinical_risk_score >= 20 THEN '🔎 TIER 3: TARGETED POST-MARKET REGISTRY COHORT'
                ELSE '✅ TIER 4: ROUTINE POST-MARKETING SURVEILLANCE'
            END as prescriptive_regulatory_action,
            CASE 
                WHEN clinical_risk_score >= 65 OR (prr >= 2.5 AND fatal_count >= 1) THEN 
                    CONCAT('Critical disproportionality (PRR ', CAST(prr AS VARCHAR), ', 95% CI Lower ', CAST(ror_ci_lower AS VARCHAR), ') combined with ', CAST(fatal_count AS VARCHAR), ' fatalities. Immediate Boxed Warning and REMS Medication Guide revision mandated.')
                WHEN clinical_risk_score >= 40 OR (prr >= 2.0 AND hosp_count >= 2) THEN 
                    CONCAT('Elevated signal (PRR ', CAST(prr AS VARCHAR), ') with significant hospitalizations (', CAST(hosp_count AS VARCHAR), ' cases). Require baseline organ panel monitoring.')
                WHEN clinical_risk_score >= 20 THEN 
                    'Moderate epidemiological signal. Sponsor must establish prospective 12-month registry cohort.'
                ELSE 
                    'Signal within acceptable baseline variability. Maintain standard FAERS quarterly reporting.'
            END as clinical_decision_rationale
        FROM signal_scored
        ORDER BY clinical_risk_score DESC, prr DESC;
    """)
    print("   -> Prescriptive regulatory decision engine built.")
    
    print("\n" + "="*85)
    print("🚨 TOP FDA POTENTIAL SAFETY SIGNALS DETECTED (PRR >= 2.0 & ROR CI > 1.0)")
    print("="*85)
    signals_df = con.execute("""
        SELECT 
            drug_name,
            adverse_reaction,
            report_count as cases,
            fatal_count as deaths,
            prr as PRR,
            ror as ROR,
            ror_ci_lower as CI_Low,
            ror_ci_upper as CI_High,
            fda_signal_status
        FROM mart_fda_safety_signals
        WHERE fda_signal_status != 'MONITORED BASELINE'
        LIMIT 6;
    """).df()
    print(signals_df.to_string(index=False))
    print("="*85)
    
    print("\n" + "="*85)
    print("💊 PHARMACEUTICAL DRUGS WITH HIGHEST DOCUMENTED FATALITY RATES")
    print("="*85)
    fatality_df = con.execute("""
        SELECT 
            drug_name,
            total_patient_cases as cases,
            fatal_events as deaths,
            hospitalizations,
            fatality_rate_pct as fatality_pct
        FROM mart_drug_fatality_risk
        LIMIT 5;
    """).df()
    print(fatality_df.to_string(index=False))
    print("="*85 + "\n")
    
    con.close()

if __name__ == "__main__":
    run_epidemiology_models()
