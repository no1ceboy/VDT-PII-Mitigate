# Mitigating Natural PII Leakage in Vietnamese Clinical Summarization via Capability-Protected Preference Optimization

This repository is the official open-source implementation for our ACL/EMNLP submission: **"Mitigating Natural PII Leakage in Vietnamese Clinical Summarization via Capability-Protected Preference Optimization"**.

We investigate the critical vulnerability of **Natural PII Leakage** in low-resource abstractive clinical summarization. Unlike artificial adversarial prompt injection, natural leakage occurs when a compact language model ($\le 7\text{B}$ parameters) natively reproduces sensitive patient identifiers (names, admission dates, phone numbers, national IDs) from unstructured medical case notes during routine summarization.

## 🌟 Overview

1. **Extrinsic Defenses:** We evaluate zero-shot instruction guardrailing and inference-time heuristic filters (regex + NER masking wrappers) in low-resource clinical summarization workflows.
2. **Intrinsic Parametric Alignment via DPO:** We introduce `vdt_pii_dpo`, an empirically curated contrastive preference dataset of 489 clinical pairs. Parameter-Efficient Fine-Tuning via Direct Preference Optimization (QLoRA DPO) internalizes a redaction policy directly into the model weights ($\pi_\theta$) without auxiliary middleware processing.
3. **The Privacy-Utility Pareto Frontier (OGPSA-DPO):** To mitigate the **Alignment Tax** (loss of general summarization capability), we implement **Orthogonal Gradient Projection for Subspace Alignment (OGPSA-DPO)** using an anchor corpus from VLSP to project preference updates orthogonally away from the general language subspace.

---

## 🏛️ Repository Architecture

```text
VDT-PII-Mitigate/
├── README.md                  # This document
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
│   ├── evaluate_ragas_judge.py  # LLM-as-a-Judge semantic quality scoring
│   ├── calculate_real_stats.py  # Calculates Table 1 dataset properties
│   └── calculate_table2_metrics.py # Calculates Table 2 privacy metrics
└── results/                   # Experimental logs and benchmark archives
    ├── benchmarks/            # Raw JSON reports for evaluation tables
    └── figures/               # High-resolution training dynamics diagrams
```

---

## 🚀 Quick Start & Installation

### 1. Clone & Setup Environment
```powershell
# Clone the repository
git clone https://github.com/no1ceboy/VDT-PII-Mitigate.git
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
Generates the contrastive clinical preference pairs (`vdt_pii_dpo`) and formats the general domain summarization examples from VLSP:
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
Evaluates all defense paradigms on our unseen holdout clinical evaluation benchmark and general domain VLSP test set:
```powershell
.\scripts\03_run_evaluations.ps1
```

---

## 🛡️ License
This project is licensed under the MIT License. See `LICENSE` for details.
