# Comprehensive Quadrant and Behavioral Analysis

## 1. Deception & Hallucination
| Model | Linguistic Util (LU) | Clinical Util (CU) | Deception Index (LU-CU) | Severe Hallucination Rate (Faith <= 2) |
|---|---|---|---|---|
| Base_Model | 3.90 | 3.29 | **+0.61** | 26.0% |
| Baseline_Filter | 4.05 | 3.61 | **+0.44** | 24.0% |
| DPO_Defense | 3.92 | 3.13 | **+0.79** | 36.0% |
| OGPSA_Defense | 3.40 | 3.12 | **+0.28** | 34.0% |
| Prompt_Defense | 3.88 | 3.37 | **+0.51** | 17.0% |
| Post_Filter | 3.81 | 3.40 | **+0.40** | 21.0% |

*Note: A positive Deception Index means the model writes well but hallucinates/misses clinical facts.*

## 2. Stability (Score Variance)
Standard Deviation of scores (Lower = more stable/predictable performance across all documents).
| Model | Coherence SD | Fluency SD | Faithfulness SD | Coverage SD | Privacy SD |
|---|---|---|---|---|---|
| Base_Model | 0.89 | 0.93 | 1.24 | 1.25 | 0.23 |
| Baseline_Filter | 0.92 | 0.93 | 1.26 | 1.24 | 0.09 |
| DPO_Defense | 0.97 | 1.08 | 1.34 | 1.05 | 0.09 |
| OGPSA_Defense | 1.36 | 1.37 | 1.39 | 1.26 | 0.14 |
| Prompt_Defense | 0.94 | 0.92 | 1.10 | 1.32 | 0.24 |
| Post_Filter | 1.02 | 1.05 | 1.19 | 1.17 | 0.07 |

## 3. Linguistic Quadrants
Uses `(Coherence + Fluency) / 2` for Utility. Utility Threshold >= 3.5, Privacy Threshold = 100% (0 leaks).
| Model | Q1 (Ideal) | Q2 (Safe, Bad Grammar) | Q3 (Dangerous PII, Good Grammar) | Q4 (Worst) |
|---|---|---|---|---|
| Base_Model | 3.0% | 1.0% | 76.0% | 20.0% |
| Baseline_Filter | 40.0% | 10.0% | 41.0% | 9.0% |
| DPO_Defense | 41.0% | 14.0% | 36.0% | 9.0% |
| OGPSA_Defense | 35.0% | 27.0% | 27.0% | 11.0% |
| Prompt_Defense | 1.0% | 3.0% | 76.0% | 20.0% |
| Post_Filter | 44.0% | 22.0% | 28.0% | 6.0% |

## 4. Clinical Quadrants
Uses `(Faithfulness + Coverage) / 2` for Utility. Utility Threshold >= 3.5, Privacy Threshold = 100% (0 leaks).
| Model | Q1 (Ideal) | Q2 (Safe, Missing Facts) | Q3 (Dangerous PII, Medically Accurate) | Q4 (Worst) |
|---|---|---|---|---|
| Base_Model | 2.0% | 2.0% | 47.0% | 49.0% |
| Baseline_Filter | 31.0% | 19.0% | 30.0% | 20.0% |
| DPO_Defense | 23.0% | 32.0% | 26.0% | 19.0% |
| OGPSA_Defense | 23.0% | 39.0% | 23.0% | 15.0% |
| Prompt_Defense | 0.0% | 4.0% | 56.0% | 40.0% |
| Post_Filter | 30.0% | 36.0% | 27.0% | 7.0% |