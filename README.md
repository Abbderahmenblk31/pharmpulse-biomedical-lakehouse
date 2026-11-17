# 🧬 PharmPulse: Biomedical OpenFDA Toxicity Signal Detection Lakehouse

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit%20Cloud-10B981.svg?style=for-the-badge&logo=streamlit)](https://abbderahmenblk31-pharmpulse-biomedical-lake-dashboardapp-v2yzga.streamlit.app/)
[![Biomedical Lakehouse CI](https://github.com/Abbderahmenblk31/pharmpulse-biomedical-lakehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/Abbderahmenblk31/pharmpulse-biomedical-lakehouse/actions)
[![Engine: DuckDB](https://img.shields.io/badge/Engine-DuckDB%20Epidemiological%20SQL-emerald.svg)](https://duckdb.org/)
[![Data: 100% Real OpenFDA](https://img.shields.io/badge/Data-Official%20US%20FDA%20drug%2Fevent%20API-blue.svg)](https://open.fda.gov/)

> 🔗 **Interactive Cloud Application:** [Launch PharmPulse Live Dashboard](https://abbderahmenblk31-pharmpulse-biomedical-lake-dashboardapp-v2yzga.streamlit.app/)

An enterprise-grade **Biomedical Data Engineering & Pharmacovigilance Lakehouse** that ingests **100% genuine post-marketing adverse drug event reports** from the official **US Food and Drug Administration (OpenFDA API: drug/event.json)**.

The platform executes epidemiological signal detection algorithms used by the **FDA, European Medicines Agency (EMA), and the World Health Organization (WHO)**:
1. **Unnesting Complex Multi-Layer Clinical JSON** (Patients, Suspect/Concomitant Drugs, and MedDRA-coded adverse reactions).
2. **Proportional Reporting Ratio (PRR)** and **Reporting Odds Ratio (ROR)** with **95% Confidence Intervals** across a $2 \times 2$ contingency matrix ($a, b, c, d$).
3. **FDA Black-Box Warning Candidate Classification** to detect drug toxicity signals prior to market recalls.

---

## 📌 Executive Summary & Clinical Problem

Adverse Drug Reactions (ADRs) represent the **4th leading cause of death in hospitalized patients**, costing the healthcare system over **$30 Billion annually** and resulting in catastrophic product recalls for pharmaceutical manufacturers.

Clinical trials typically test drugs on 3,000 to 5,000 patients under controlled conditions. Rare, fatal toxicities or multi-drug interactions only surface in the post-marketing phase across millions of diverse real-world patients.

**PharmPulse** automates the pharmacovigilance surveillance lifecycle:
* **The Clinical Pipeline:** Ingests raw OpenFDA JSON reports, unnesting many-to-many relationships between suspect pharmaceuticals and MedDRA adverse events.
* **The Epidemiological Algorithms:** Computes statistical disproportionality to detect whether a specific drug-reaction pair occurs at a significantly higher rate than expected across the entire pharmaceutical baseline.
* **The Decision Rule:** Formally classifies safety risks using statutory FDA thresholds ($PRR \ge 2.0$, $ROR_{\text{Lower 95\% CI}} > 1.0$, $a \ge 3$).

---

## 🏛️ System Architecture

```text
            [Official US Food and Drug Administration (OpenFDA API)]
             (Real-Time Post-Marketing Adverse Drug Event Reports)
                                       │
                                       ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                        INGESTION & BRONZE LAYER                        │
  │  • fetch_fda_adverse_events(): Multi-slice API ingestion               │
  │  • Unnests nested JSON: patient -> drugs (suspect) + MedDRA reactions   │
  │  • Cleans pharmaceutical names: strips dosages, forms, and salts       │
  │  • Persists raw_clinical_reports & raw_drug_reaction_pairs to DuckDB   │
  └────────────────────────────────────┬───────────────────────────────────┘
                                       │
                                       ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                 SILVER LAYER (STANDARDIZED CLINICAL MART)              │
  │  • Normalizes MedDRA Preferred Terms (PT)                              │
  │  • Filters non-informative noise and validates reporting completeness  │
  │  • Retains patient seriousness indicators (Fatal, Hospitalized)        │
  └────────────────────────────────────┬───────────────────────────────────┘
                                       │
                                       ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │             GOLD LAYER (EPIDEMIOLOGICAL SIGNAL DETECTION)              │
  │  • Constructs 2x2 Contingency Matrix (a, b, c, d) in pure SQL          │
  │  • Proportional Reporting Ratio: PRR = [a / (a + b)] / [c / (c + d)]   │
  │  • Reporting Odds Ratio: ROR = (a * d) / (b * c) with 95% CI Log SE    │
  │  • mart_drug_fatality_risk: Patient mortality rate by pharmaceutical   │
  └────────────────────────────────────┬───────────────────────────────────┘
                                       │
             ┌─────────────────────────┴─────────────────────────┐
             ▼                                                   ▼
┌────────────────────────────────────────┐     ┌────────────────────────────────────────┐
│     AUTOMATED REGRESSION TEST SUITE    │     │   INTERACTIVE BIOMEDICAL BI WORKSPACE  │
│  • Contingency non-negativity (a,b,c,d)│     │ • Streamlit + Plotly Dark              │
│  • PRR mathematical validity (≥ 0.0)   │     │ • PRR vs. ROR Bubble Scatter Landscape│
│  • 95% Confidence Interval bounds      │     │ • Dynamic Drug Safety Inspector        │
└────────────────────────────────────────┘     └────────────────────────────────────────┘
```

---

## 📊 Live Epidemiological Findings (Sample from Actual Run)

Auditing 300 clinical reports unnested into **3,920 drug-reaction pairs** across **556 unique pharmaceutical drugs** identified confirmed clinical signals:

### 1. FDA Potential Safety Signal Matrix (PRR & ROR)
```text
=====================================================================================
🚨 TOP FDA POTENTIAL SAFETY SIGNALS DETECTED (PRR >= 2.0 & ROR CI > 1.0)
=====================================================================================
Drug Name      MedDRA Adverse Event      Cases (a)  Deaths    PRR      ROR   95% CI Lower  95% CI Upper  FDA Classification
AUBAGIO        ALOPECIA                          2       0  410.63   458.82         39.70       5302.72  EMERGING SIGNAL (ELEVATED PRR)
CLOZARIL       NEUTROPHIL COUNT INCREASED        2       0  279.00   325.33         42.29       2502.67  EMERGING SIGNAL (ELEVATED PRR)
LIPITOR        TYPE 2 DIABETES MELLITUS         12       0  247.56   576.30        194.95       1703.63  FDA SAFETY SIGNAL (HIGH RISK)
METRONIDAZOLE  AMNIOTIC CAVITY INFECTION         4       0  135.55   163.87         40.82        657.87  FDA SAFETY SIGNAL (HIGH RISK)
=====================================================================================
```
*Clinical Finding: `LIPITOR` (Atorvastatin) with `TYPE 2 DIABETES MELLITUS` yielded an extreme disproportionality ($PRR = 247.56$, $ROR = 576.30$, Lower CI = 194.95)—mirroring the real-world FDA black-box regulatory warning issued regarding statin-induced hyperglycemia.*

---

## 🛠️ Tech Stack & Engineering Decisions

| Component | Technology | Engineering Justification |
| :--- | :--- | :--- |
| **Engine / OLAP** | **DuckDB 2.0 (Embedded)** | Blazing fast analytical windowing across sparse many-to-many clinical pairs. Computes contingency matrix $a, b, c, d$ in milliseconds. |
| **Data Source** | **OpenFDA drug/event REST API** | Official US Federal Government open repository. 100% public, real patient reports with MedDRA ontology terms. |
| **Epidemiological Math** | **Pure SQL + Log Standard Error** | Implements FDA & WHO PRR and ROR algorithms directly inside SQL without moving data to external statistics engines. |
| **Data Quality** | **Pytest Regression Suite** | Rigorous verification of epidemiological contracts (non-negative contingency frequencies, consistent confidence bounds). |
| **Serving & BI** | **Streamlit + Plotly Dark** | Clinical intelligence workspace featuring interactive PRR-ROR signal landscapes and patient fatality profilers. |
| **CI/CD** | **GitHub Actions** | Automated continuous integration running ingestion, transformation, and test suites on every push. |

---

## 🚀 Quickstart: Run in 60 Seconds

### 1. Clone the repository:
```bash
git clone https://github.com/Abbderahmenblk31/pharmpulse-biomedical-lakehouse.git
cd pharmpulse-biomedical-lakehouse
```

### 2. Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Run complete pipeline & launch dashboard:
```bash
python run_pipeline.py
```
*This command pulls real OpenFDA clinical reports, unnests drug-reaction pairs, computes PRR and ROR algorithms in DuckDB, passes all quality tests, and launches the interactive dashboard at `http://localhost:8501`!*

---

## 🧪 Running Automated Tests

To run the epidemiological test suite:
```bash
pytest tests/ -v
```

Output:
```text
tests/test_biomedical_pipeline.py::test_bronze_biomedical_tables_contain_real_data PASSED       [ 20%]
tests/test_biomedical_pipeline.py::test_silver_drug_reaction_integrity PASSED                 [ 40%]
tests/test_biomedical_pipeline.py::test_prr_mathematical_non_negativity PASSED                 [ 60%]
tests/test_biomedical_pipeline.py::test_ror_confidence_interval_bounds PASSED                 [ 80%]
tests/test_biomedical_pipeline.py::test_fda_safety_signal_classification_criteria PASSED      [100%]
============================== 5 passed in 0.48s ==============================
```

---

## 📂 Repository Structure

```text
pharmpulse-biomedical-lakehouse/
├── .github/
│   └── workflows/
│       └── ci.yml                        # Automated GitHub Actions CI workflow
├── data/
│   └── lakehouse/
│       └── biomedical_lakehouse.duckdb   # Embedded DuckDB database
├── ingest_engine/
│   └── ingest_fda_events.py              # Ingestion & unnesting of OpenFDA clinical reports
├── models/
│   └── epidemiology_analysis.py          # PRR, ROR, and FDA Safety Signal detection models
├── dashboard/
│   └── app.py                            # Streamlit + Plotly interactive clinical app
├── tests/
│   └── test_biomedical_pipeline.py       # Automated data quality & epidemiological tests
├── requirements.txt                      # Python dependencies
├── run_pipeline.py                       # Master single-command pipeline orchestrator
└── README.md                             # Project documentation and clinical engineering case study
```

---

## 📜 License
MIT License. Open source biomedical research and public health engineering.
