"""
PharmPulse - Biomedical Pharmacovigilance & Safety Dashboard
============================================================
A clinical intelligence application built on DuckDB Lakehouse and real-time
OpenFDA adverse drug event telemetry. Detects statistical disproportionality signals
(PRR & ROR) to identify drug toxicity risks prior to market recalls.
"""

import os
import sys
import duckdb
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Page Configuration
st.set_page_config(
    page_title="PharmPulse | Biomedical FDA Safety Lakehouse",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "lakehouse", "biomedical_lakehouse.duckdb")

@st.cache_data(ttl=60)
def load_biomedical_data():
    # Cloud auto-init fallback if lakehouse db is missing
    if not os.path.exists(DB_PATH):
        import subprocess
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "ingest_engine", "ingest_fda_events.py")], check=True)
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "models", "epidemiology_analysis.py")], check=True)
        
    con = duckdb.connect(DB_PATH, read_only=True)
    
    signals_df = con.execute("SELECT * FROM mart_fda_safety_signals ORDER BY prr DESC;").df()
    fatality_df = con.execute("SELECT * FROM mart_drug_fatality_risk ORDER BY fatal_events DESC;").df()
    
    try:
        regulatory_df = con.execute("SELECT * FROM mart_prescriptive_regulatory_actions ORDER BY clinical_risk_score DESC;").df()
    except Exception:
        regulatory_df = pd.DataFrame()
    
    summary_stats = con.execute("""
        SELECT 
            (SELECT COUNT(*) FROM raw_clinical_reports) as total_reports,
            (SELECT COUNT(DISTINCT drug_name) FROM silver_drug_safety_pairs) as unique_drugs,
            (SELECT COUNT(*) FROM mart_fda_safety_signals WHERE fda_signal_status LIKE '%SAFETY SIGNAL%') as active_signals,
            (SELECT SUM(is_hospitalized) FROM raw_clinical_reports) as total_hospitalizations,
            (SELECT SUM(is_fatal) FROM raw_clinical_reports) as total_fatalities
    """).fetchone()
    
    con.close()
    return signals_df, fatality_df, summary_stats, regulatory_df

# Title & Executive Header
st.markdown("""
<div style='background-color: #042940; padding: 22px; border-radius: 12px; margin-bottom: 25px; border-left: 6px solid #10b981;'>
    <div style='display: flex; justify-content: space-between; align-items: center;'>
        <div>
            <h1 style='color: #ffffff; margin: 0; font-size: 26px;'>🧬 PharmPulse: Biomedical Pharmacovigilance Lakehouse</h1>
            <p style='color: #94a3b8; margin: 6px 0 0 0; font-size: 14px;'>
                Detecting <b>Drug Toxicity & Black-Box Safety Signals</b> via OpenFDA Telemetry, PRR, and ROR Algorithms
            </p>
        </div>
        <div style='background-color: #005C53; padding: 10px 18px; border-radius: 8px; border: 1px solid #9FC131; text-align: right;'>
            <span style='color: #e2e8f0; font-size: 12px;'>Data Source:</span> <b style='color: #DBF227;'>OpenFDA drug/event API</b> | 
            <span style='color: #e2e8f0; font-size: 12px;'>Standard:</span> <b style='color: #ffffff;'>FDA & WHO MedDRA</b>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

try:
    signals_df, fatality_df, summary, regulatory_df = load_biomedical_data()
except Exception as e:
    st.error(f"Failed to connect to Biomedical Lakehouse: {e}")
    st.stop()

# Top KPI Metric Cards
total_reports = int(summary[0])
unique_drugs = int(summary[1])
active_signals = int(summary[2])
total_hospitalizations = int(summary[3])
total_fatalities = int(summary[4])

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(
        "📋 Clinical Reports Screened",
        f"{total_reports:,} Cases",
        delta="Official OpenFDA Data"
    )
with col2:
    st.metric(
        "💊 Pharmaceuticals Audited",
        f"{unique_drugs:,} Entities",
        delta="RxNorm Standardized"
    )
with col3:
    st.metric(
        "🚨 High-Risk Safety Signals",
        f"{active_signals} Signals",
        delta="PRR ≥ 2.0 & ROR Lower CI > 1.0",
        delta_color="inverse"
    )
with col4:
    st.metric(
        "🏥 Hospitalization Burden",
        f"{total_hospitalizations:,} Patients",
        delta=f"{total_fatalities:,} Fatal Cases Recorded",
        delta_color="inverse"
    )

st.markdown("---")

# Main Investigation Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "🚨 FDA Safety Signals (PRR & ROR)",
    "💊 Drug Fatality & Clinical Severity",
    "🔍 Targeted Drug Safety Inspector",
    "🤖 Prescriptive Regulatory & Clinical Action Engine"
])

with tab1:
    st.subheader("Statistical Disproportionality Signal Matrix (PRR vs. ROR)")
    st.markdown("""
    Under **FDA and WHO pharmacovigilance protocols**, potential toxicity signals are identified when a drug exhibits 
    a **Proportional Reporting Ratio (PRR) ≥ 2.0**, an event count $a \ge 3$, and a **Reporting Odds Ratio (ROR) Lower 95% CI > 1.0**.
    """)
    
    # Filter high signals
    sig_filtered = signals_df[signals_df["report_count"] >= 2].copy()
    
    fig_scatter = px.scatter(
        sig_filtered.head(50),
        x="prr",
        y="ror",
        size="report_count",
        color="fda_signal_status",
        color_discrete_map={
            "FDA POTENTIAL SAFETY SIGNAL (HIGH RISK)": "#ef4444",
            "EMERGING SIGNAL (ELEVATED PRR)": "#f59e0b",
            "MONITORED BASELINE": "#64748b"
        },
        hover_name="drug_name",
        hover_data=["adverse_reaction", "report_count", "ror_ci_lower", "ror_ci_upper"],
        title="Drug-Reaction Signal Landscape (PRR vs. ROR with 95% Confidence Bounds)",
        labels={"prr": "Proportional Reporting Ratio (PRR)", "ror": "Reporting Odds Ratio (ROR)"}
    )
    fig_scatter.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig_scatter, use_container_width=True)
    
    st.subheader("Black-Box Warning Candidate Scorecard")
    st.dataframe(
        signals_df[[
            "drug_name", "adverse_reaction", "report_count", "fatal_count", "hosp_count",
            "prr", "ror", "ror_ci_lower", "ror_ci_upper", "fda_signal_status"
        ]].rename(columns={
            "drug_name": "Pharmaceutical Drug",
            "adverse_reaction": "MedDRA Adverse Reaction",
            "report_count": "Documented Cases (a)",
            "fatal_count": "Fatalities",
            "hosp_count": "Hospitalized",
            "prr": "PRR Score",
            "ror": "ROR Odds",
            "ror_ci_lower": "ROR 95% CI Low",
            "ror_ci_upper": "ROR 95% CI High",
            "fda_signal_status": "FDA Signal Status"
        }),
        use_container_width=True
    )

with tab2:
    st.subheader("Pharmaceutical Fatality & Severity Profiler")
    st.markdown("Analysis of drugs associated with highest clinical hospitalization and patient mortality rates:")
    
    fig_fatality = px.bar(
        fatality_df.head(12),
        x="drug_name",
        y=["fatal_events", "hospitalizations"],
        barmode="group",
        title="Patient Outcomes by Drug: Fatal Events vs. Hospitalizations",
        labels={"value": "Total Patient Count", "drug_name": "Pharmaceutical Entity", "variable": "Clinical Outcome"},
        color_discrete_map={"fatal_events": "#ef4444", "hospitalizations": "#3b82f6"}
    )
    fig_fatality.update_layout(template="plotly_dark", height=430)
    st.plotly_chart(fig_fatality, use_container_width=True)
    
    st.dataframe(
        fatality_df[[
            "drug_name", "total_patient_cases", "fatal_events", "hospitalizations",
            "fatality_rate_pct", "hospitalization_rate_pct"
        ]].rename(columns={
            "drug_name": "Pharmaceutical Entity",
            "total_patient_cases": "Total Patients",
            "fatal_events": "Documented Fatalities",
            "hospitalizations": "Hospitalized Cases",
            "fatality_rate_pct": "Mortality Rate (%)",
            "hospitalization_rate_pct": "Hospitalization Rate (%)"
        }),
        use_container_width=True
    )

with tab3:
    st.subheader("Individual Drug Safety Profiler")
    
    drug_list = sorted(list(signals_df["drug_name"].unique()))
    selected_drug = st.selectbox("Select Pharmaceutical Product to Inspect:", drug_list, index=0)
    
    drug_profile = signals_df[signals_df["drug_name"] == selected_drug]
    
    st.markdown(f"### Adverse Event Portfolio for **{selected_drug}**")
    st.dataframe(
        drug_profile[[
            "adverse_reaction", "report_count", "prr", "ror", "ror_ci_lower", "ror_ci_upper", "fda_signal_status"
        ]].rename(columns={
            "adverse_reaction": "Adverse Reaction (MedDRA)",
            "report_count": "Patient Cases",
            "prr": "PRR Score",
            "ror": "ROR Odds",
            "ror_ci_lower": "95% CI Lower",
            "ror_ci_upper": "95% CI Upper",
            "fda_signal_status": "Signal Alert Level"
        }),
        use_container_width=True
    )

with tab4:
    st.subheader("🤖 Prescriptive Decision Intelligence: Regulatory Action & Clinical Triage")
    st.caption("Automated clinical & regulatory mandates based on Disproportionality Strength (PRR, ROR 95% CI Lower) and Mortality/Hospitalization Ratios.")
    
    if not regulatory_df.empty:
        t1_count = int((regulatory_df["prescriptive_regulatory_action"].str.contains("TIER 1")).sum())
        t2_count = int((regulatory_df["prescriptive_regulatory_action"].str.contains("TIER 2")).sum())
        t3_count = int((regulatory_df["prescriptive_regulatory_action"].str.contains("TIER 3")).sum())
        high_risk_pairs = len(regulatory_df[regulatory_df["clinical_risk_score"] >= 40])
        
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("🚨 Tier 1: Boxed Warning & REMS", f"{t1_count} Drug-Event Pairs", delta="Critical Regulatory Action", delta_color="inverse")
        pc2.metric("⚠️ Tier 2: Label Restrictions", f"{t2_count} Drug-Event Pairs", delta="Mandatory Organ Baseline", delta_color="inverse")
        pc3.metric("🔎 Tier 3: Prospective Registries", f"{t3_count} Drug-Event Pairs", delta="12-Month Cohort Mandate")
        pc4.metric("Elevated Clinical Risk Signals", f"{high_risk_pairs} Pairs", delta="Score ≥ 40/100")
        
        # Action selector
        reg_filter = st.radio("Filter Prescriptive Regulatory Directive:", ["All Directives", "🚨 Tier 1 (Boxed Warning / REMS)", "⚠️ Tier 2 (Label Restriction)", "🔎 Tier 3 (Registry Cohort)"], horizontal=True)
        display_reg = regulatory_df.copy()
        if reg_filter == "🚨 Tier 1 (Boxed Warning / REMS)":
            display_reg = display_reg[display_reg["prescriptive_regulatory_action"].str.contains("TIER 1")]
        elif reg_filter == "⚠️ Tier 2 (Label Restriction)":
            display_reg = display_reg[display_reg["prescriptive_regulatory_action"].str.contains("TIER 2")]
        elif reg_filter == "🔎 Tier 3 (Registry Cohort)":
            display_reg = display_reg[display_reg["prescriptive_regulatory_action"].str.contains("TIER 3")]
            
        st.markdown("### 📋 Prescriptive Clinical & Regulatory Action Matrix")
        st.dataframe(
            display_reg[[
                "drug_name", "adverse_reaction", "report_count", "fatal_count", "hosp_count",
                "prr", "ror_ci_lower", "clinical_risk_score", "prescriptive_regulatory_action", "clinical_decision_rationale"
            ]].rename(columns={
                "drug_name": "Pharmaceutical Entity",
                "adverse_reaction": "MedDRA Reaction",
                "report_count": "Patient Cases",
                "fatal_count": "Deaths",
                "hosp_count": "Hospitalized",
                "prr": "PRR Disproportionality",
                "ror_ci_lower": "95% CI Lower Bound",
                "clinical_risk_score": "Clinical Risk Score (0-100)",
                "prescriptive_regulatory_action": "Prescriptive Regulatory Directive",
                "clinical_decision_rationale": "Medical Board Decision Rationale"
            }),
            use_container_width=True
        )
        
        # Clinical Risk vs PRR Scatter Plot
        st.markdown("### 📊 Clinical Risk Severity Landscape")
        fig_reg = px.scatter(
            regulatory_df.head(30),
            x="prr",
            y="clinical_risk_score",
            size="report_count",
            color="prescriptive_regulatory_action",
            color_discrete_map={
                "🚨 TIER 1: MANDATORY BLACK-BOX WARNING & REMS": "#ef4444",
                "⚠️ TIER 2: CONTRAINDICATION RESTRICTION & LABEL REVISION": "#f59e0b",
                "🔎 TIER 3: TARGETED POST-MARKET REGISTRY COHORT": "#3b82f6",
                "✅ TIER 4: ROUTINE POST-MARKETING SURVEILLANCE": "#10b981"
            },
            hover_name="drug_name",
            hover_data=["adverse_reaction", "fatal_count", "ror_ci_lower"],
            title="Clinical Risk Score (0-100) vs PRR Disproportionality by Regulatory Tier",
            labels={"prr": "Proportional Reporting Ratio (PRR)", "clinical_risk_score": "Composite Risk Score (0-100)"}
        )
        fig_reg.update_layout(template="plotly_dark", height=430)
        st.plotly_chart(fig_reg, use_container_width=True)
    else:
        st.info("Prescriptive regulatory engine initializing. Please click 'Rerun Live OpenFDA Clinical Ingestion'.")

st.sidebar.title("🧬 Pharmacovigilance")
st.sidebar.info(f"""
- **Standards:** FDA / WHO MedDRA
- **Active Signals:** `{active_signals}` Detected
- **PRR Cutoff:** `≥ 2.0`
- **Engine:** DuckDB Epidemiological SQL
""")

if st.sidebar.button("🔄 Rerun Live OpenFDA Clinical Ingestion"):
    with st.spinner("Streaming real-time FDA reports & recalculating PRR/ROR..."):
        import subprocess
        subprocess.run(["python", os.path.join(BASE_DIR, "ingest_engine", "ingest_fda_events.py")], check=True)
        subprocess.run(["python", os.path.join(BASE_DIR, "models", "epidemiology_analysis.py")], check=True)
        st.cache_data.clear()
        st.success("Biomedical Lakehouse refreshed with latest FDA adverse events!")
        st.rerun()
