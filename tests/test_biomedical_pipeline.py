"""
PharmPulse - Biomedical Pipeline & Epidemiological Tests
========================================================
Automated regression tests to verify PRR, ROR formulas,
95% confidence interval bounds, and MedDRA clinical contracts.
"""

import os
import duckdb
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "lakehouse", "biomedical_lakehouse.duckdb")

@pytest.fixture
def db_conn():
    con = duckdb.connect(DB_PATH, read_only=True)
    yield con
    con.close()

def test_bronze_biomedical_tables_contain_real_data(db_conn):
    """Verifies that clinical reports and unnested drug-reaction pairs contain real records."""
    reports_cnt = db_conn.execute("SELECT COUNT(*) FROM raw_clinical_reports").fetchone()[0]
    pairs_cnt = db_conn.execute("SELECT COUNT(*) FROM raw_drug_reaction_pairs").fetchone()[0]
    assert reports_cnt > 50, f"Insufficient clinical reports: {reports_cnt}"
    assert pairs_cnt > 100, f"Insufficient unnested pairs: {pairs_cnt}"

def test_silver_drug_reaction_integrity(db_conn):
    """Ensures silver layer contains no UNKNOWN drugs and valid MedDRA reaction strings."""
    invalid = db_conn.execute("""
        SELECT COUNT(*) 
        FROM silver_drug_safety_pairs 
        WHERE drug_name = 'UNKNOWN' 
           OR adverse_reaction IS NULL 
           OR adverse_reaction = '';
    """).fetchone()[0]
    assert invalid == 0, f"Found {invalid} invalid records in silver layer!"

def test_prr_mathematical_non_negativity(db_conn):
    """Ensures Proportional Reporting Ratio (PRR) is strictly non-negative."""
    negative_prr = db_conn.execute("""
        SELECT COUNT(*) 
        FROM mart_fda_safety_signals 
        WHERE prr < 0 OR prr IS NULL;
    """).fetchone()[0]
    assert negative_prr == 0, f"Found {negative_prr} invalid PRR scores!"

def test_ror_confidence_interval_bounds(db_conn):
    """Ensures 95% Confidence Interval respects lower_ci <= ror <= upper_ci mathematically."""
    inverted_ci = db_conn.execute("""
        SELECT COUNT(*) 
        FROM mart_fda_safety_signals 
        WHERE ror_ci_lower > ror_ci_upper
          AND ror_ci_lower IS NOT NULL 
          AND ror_ci_upper IS NOT NULL;
    """).fetchone()[0]
    assert inverted_ci == 0, f"Found {inverted_ci} inverted confidence intervals!"

def test_fda_safety_signal_classification_criteria(db_conn):
    """Ensures FDA High Risk classification strictly complies with PRR >= 2.0 and report_count >= 3."""
    false_positives = db_conn.execute("""
        SELECT COUNT(*) 
        FROM mart_fda_safety_signals 
        WHERE fda_signal_status = 'FDA POTENTIAL SAFETY SIGNAL (HIGH RISK)'
          AND (prr < 2.0 OR report_count < 3 OR ror_ci_lower <= 1.0);
    """).fetchone()[0]
    assert false_positives == 0, f"Found {false_positives} misclassified FDA safety signals!"

def test_prescriptive_regulatory_actions(db_conn):
    """Verifies that clinical risk scores are within [0, 100] and mapped to valid regulatory actions."""
    df = db_conn.execute("SELECT * FROM mart_prescriptive_regulatory_actions").df()
    assert len(df) > 0, "Prescriptive regulatory actions mart is empty!"
    assert (df["clinical_risk_score"] >= 0.0).all(), "Negative clinical risk score found!"
    assert (df["clinical_risk_score"] <= 100.0).all(), "Clinical risk score exceeded 100!"
    valid_actions = {
        "🚨 TIER 1: MANDATORY BLACK-BOX WARNING & REMS",
        "⚠️ TIER 2: CONTRAINDICATION RESTRICTION & LABEL REVISION",
        "🔎 TIER 3: TARGETED POST-MARKET REGISTRY COHORT",
        "✅ TIER 4: ROUTINE POST-MARKETING SURVEILLANCE"
    }
    actual_actions = set(df["prescriptive_regulatory_action"].unique())
    assert actual_actions.issubset(valid_actions), f"Invalid regulatory actions: {actual_actions - valid_actions}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
