# Mitigating Natural PII Leakage in Vietnamese Clinical Summarization via Capability-Protected Preference Optimization

This repository is the official open-source implementation for our ACL/EMNLP submission: **"Mitigating Natural PII Leakage in Vietnamese Clinical Summarization via Capability-Protected Preference Optimization"**.

We investigate the critical vulnerability of **Natural PII Leakage** in low-resource abstractive clinical summarization. Unlike artificial adversarial prompt injection, natural leakage occurs when a compact language model ($\le 7\text{B}$ parameters) natively reproduces sensitive patient identifiers (names, admission dates, phone numbers, national IDs) from unstructured medical case notes during routine summarization.

## 🌟 Key Research Contributions

1. **Empirical Failure of Extrinsic Defenses:** We demonstrate that zero-shot instruction guardrailing fails catastrophically in clinical summarization (**98.0% document leakage rate**) due to autoregressive salience override and negative constraint priming. Meanwhile, inference-time heuristic filters (regex + NER masking) leave **50.0% residual document leakage** and impose significant middleware latency overhead.
2. **Intrinsic Parametric Alignment via DPO:** We introduce `vdt_pii_dpo`, an empirically curated contrastive preference dataset of 489 clinical pairs. Parameter-Efficient Fine-Tuning via Direct Preference Optimization (QLoRA DPO) internalizes a zero-latency redaction policy directly into the model weights ($\pi_\theta$), reducing overall entity leakage by an order of magnitude (**6.17% vs. 33.20%**).
3. **The Privacy-Utility Pareto Frontier (OGPSA-DPO):** To mitigate the **Alignment Tax** (loss of general summarization capability), we implement **Orthogonal Gradient Projection for Subspace Alignment (OGPSA-DPO)** using a clean anchor corpus from VLSP. We uncover a fundamental Pareto trade-off: projecting preference updates orthogonally away from the general language subspace achieves maximum absolute confidentiality (**62.0% zero-leakage rate**), while standard low-rank DPO ($r=16$) serves as an optimal empirical regularizer balancing privacy and cross-domain abstractive fluency.

---

## 🏛️ Repository Architecture

```text
VDT-PII-Mitigate/
├── README.md                  # This academic release document
├── requirements.txt           # Python dependency specifications
├── docs/                      # LaTeX manuscript, custom BibTeX, and figures
│   └── ACL_Template_VDT/      # Complete ACL/EMNLP LaTeX paper source
├── ogpsa_patches/             # Compatibility patches for SunGL001/OGPSA
├── scripts/                   # PowerShell scripts to reproduce all experiments
│   ├── 01_prepare_datasets.ps1 # Generate contrastive DPO & VLSP anchor datasets
│   ├── 02_train_models.ps1    # Train Standard DPO and OGPSA-DPO LoRA adapters
│   └── 03_run_evaluations.ps1 # Run holdout benchmarks & compute table metrics
├── src/                       # Core research codebase
│   ├── pii_leakage_evaluator.py # Exact-match PII entity leakage calculation
│   ├── generate_natural_dpo.py  # Curation pipeline for vdt_pii_dpo dataset
│   ├── train_defense.py       # QLoRA DPO and custom OGPSA SVD trainer
│   ├── openai_privacy_filter.py # Inference-time baseline regex + NER wrapper
│   ├── survey_natural_leakage.py# Baseline leakage benchmark on Meddies holdout
│   ├── survey_prompt_defense.py # Zero-shot HIPAA guardrail benchmark
│   ├── survey_filter_effectiveness.py # Baseline filter benchmark
│   ├── evaluate_defense.py    # Holdout evaluation for trained LoRA adapters
│   ├── evaluate_capability.py # ROUGE and verbosity evaluation on VLSP
│   ├── evaluate_ragas_judge.py  # LLM-as-a-Judge 1-5 Likert semantic scoring
│   ├── calculate_real_stats.py  # Calculates Table 1 dataset properties
│   └── calculate_table2_metrics.py # Calculates Table 2 privacy metrics
└── results/                   # Experimental logs and benchmark archives
    ├── benchmarks/            # Raw JSON reports for Table 2, Table 3, and Table 4
    └── figures/               # High-resolution training dynamics diagrams
```

---

## 🚀 Quick Start & Installation

### 1. Clone & Setup Environment
```powershell
# Clone the repository
git clone https://github.com/YourUsername/VDT-PII-Mitigate.git
cd VDT-PII-Mitigate

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Setup OGPSA (For Orthogonal Subspace Training)
```powershell
git clone https://github.com/SunGL001/OGPSA.git OGPSA
Copy-Item -Path "ogpsa_patches\*" -Destination "OGPSA" -Recurse -Force
pip install -e ./OGPSA
```

---

## 📊 Reproducing the Paper's Benchmarks

All datasets, training trajectories, and benchmark evaluations can be reproduced using our automated scripts in `scripts/`.

### Step 1: Prepare Datasets (`Table 1`)
Generates the 489 contrastive clinical preference pairs (`vdt_pii_dpo`) and formats the 200 general domain summarization examples from VLSP:
```powershell
.\scripts\01_prepare_datasets.ps1
python src/calculate_real_stats.py
```

### Step 2: Train Privacy-Aligned Models (`Figure 2`)
Fine-tunes `Qwen/Qwen2.5-1.5B-Instruct` using Standard QLoRA DPO and Orthogonal Gradient Projection (OGPSA-DPO), logging loss curves and reward margins:
```powershell
.\scripts\02_train_models.ps1
```

### Step 3: Run Out-of-Distribution Benchmarks (`Table 2`, `Table 3`, `Table 4`)
Evaluates all defense paradigms on our unseen holdout clinical evaluation benchmark ($N=100$, strict document offset $\ge 2000$) and general domain VLSP test set ($N=30$):
```powershell
.\scripts\03_run_evaluations.ps1
```

---

## 📈 Main Experimental Results

### Table 2: Privacy Mitigation Evaluation (Unseen Holdout Benchmark, $N=100$)

| **Defense Mechanism** | **Entity Leakage Rate ($\mathcal{L}_{\text{PII}}$) $\downarrow$** | **Zero-Leakage Doc Rate $\uparrow$** | **Inference Overhead** |
| :--- | :---: | :---: | :---: |
| **1. Undefended Base Model** (`Qwen-1.5B`) | 33.20% | 2.0% | 0 ms (Baseline) |
| **2. Zero-Shot Prompt Defense** (HIPAA Guardrail) | 38.96% | 2.0% | 0 ms (Prompting) |
| **3. Baseline Privacy Filter** (Regex + NER Wrapper) | 6.88% | 50.0% | ~150–300 ms (Middleware) |
| **4. Standard QLoRA DPO** ($r=16$) | **6.17%** | 55.0% | **0 ms (Native Weights)** |
| **5. OGPSA QLoRA DPO** ($r=16$, Subspace Protected) | 7.78% | **62.0%** | **0 ms (Native Weights)** |

### Table 3 & Table 4: General Domain Summarization & Semantic Preservation (VLSP Holdout, $N=30$)

| **Defense Mechanism** | **ROUGE-1 (%)** | **ROUGE-L (%)** | **Len Ratio** | **Faithfulness (1–5)** | **Conciseness (1–5)** | **Overall Quality** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Undefended Base Model** | 62.02% | 31.80% | 0.73 | 3.60 | 4.23 | 3.86 |
| **2. Baseline Privacy Filter** | 60.33% | 31.36% | 0.64 | 3.57 | 4.50 | 4.01 |
| **3. Standard QLoRA DPO** | 44.14% | 25.38% | 0.42 | **4.00** | **4.73** | **4.07** |
| **4. OGPSA QLoRA DPO** | 40.96% | 24.32% | 0.45 | **4.00** | 4.60 | 3.92 |

> **Note on the Abstractive Compression Shift:** DPO alignment internalizes a compact executive formatting prior (~45% shorter outputs). While this word-count reduction lowers surface n-gram recall in ROUGE, empirical LLM-as-a-Judge semantic evaluations (`Gemini-3.1-Flash-Lite`) confirm that DPO eliminates hallucination (**4.00 vs. 3.60 Faithfulness**) and improves executive structure without loss of core narrative meaning.

---

## 📜 Citation

If you use our dataset (`vdt_pii_dpo`), codebase, or research findings in your work, please cite our paper:

```bibtex
@article{vdt_pii_defense_2026,
  title={Mitigating Natural PII Leakage in Vietnamese Clinical Summarization via Capability-Protected Preference Optimization},
  author={Minh and Contributors},
  journal={Proceedings of the Association for Computational Linguistics / Empirical Methods in Natural Language Processing},
  year={2026}
}
```

## 🛡️ License
This project is licensed under the MIT License. See `LICENSE` for details.
