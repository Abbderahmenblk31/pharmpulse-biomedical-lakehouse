"""
PharmPulse - Master Pipeline Orchestrator
=========================================
Runs full end-to-end biomedical pharmacovigilance pipeline:
1. Ingests clinical adverse drug events from OpenFDA API
2. Executes FDA PRR and ROR disproportionality signal models in DuckDB
3. Runs automated data quality and epidemiological tests
4. Launches the interactive Biomedical Safety Dashboard
"""

import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_step(title, command):
    print("\n" + "="*75)
    print(f"  {title}")
    print("="*75)
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"❌ Error encountered in: {title}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    print("""
    ===================================================================
       🧬 PHARMPULSE: BIOMEDICAL FDA TOXICITY SIGNAL LAKEHOUSE 🧬
    ===================================================================
    """)
    run_step("STEP 1: INGESTING OPENFDA ADVERSE DRUG EVENTS", [sys.executable, "ingest_engine/ingest_fda_events.py"])
    run_step("STEP 2: RUNNING PRR & ROR DISPROPORTIONALITY MODELS", [sys.executable, "models/epidemiology_analysis.py"])
    run_step("STEP 3: EXECUTING AUTOMATED EPIDEMIOLOGICAL TESTS", [sys.executable, "-m", "pytest", "tests/", "-v"])
    
    print("\n" + "="*75)
    print("  STEP 4: LAUNCHING INTERACTIVE CLINICAL SAFETY DASHBOARD")
    print("="*75)
    print("Opening Streamlit on http://localhost:8501 ...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard/app.py"], cwd=BASE_DIR)
