# VDT-PII-Mitigate: Mitigating Natural PII Leakage in Vietnamese Clinical Summarization

This repository is an open-source project and evaluation toolkit designed to detect and mitigate **Natural PII Leakage** in Vietnamese clinical document summarization.

Unlike adversarial prompt injection or jailbreak attacks, natural leakage occurs when compact language models ($\le 7\text{B}$ parameters) natively repeat sensitive patient identifiers—such as patient names, admission dates, contact phone numbers, and national identification numbers—from unstructured clinical case notes during routine abstractive summarization.

This project implements and evaluates two parameter-efficient alignment strategies to suppress natural leakage directly in model weights without relying on inference-time middleware filters:
1. **Standard QLoRA DPO:** Direct Preference Optimization fine-tuning using curated contrastive clinical preference pairs (`vdt_pii_dpo`).
2. **Capability-Protected Alignment (OGPSA-DPO):** Orthogonal Gradient Projection for Subspace Alignment, which constrains preference gradient updates to remain orthogonal to general Vietnamese language capabilities (anchored on VLSP summarization data) to prevent catastrophic forgetting.

---

## 🏛️ Repository Architecture

```text
VDT-PII-Mitigate/
├── README.md                  # Project documentation
├── requirements.txt           # Python dependency specifications
├── ogpsa_patches/             # Compatibility patches for SunGL001/OGPSA
├── scripts/                   # Automated execution pipelines
│   ├── 01_prepare_datasets.ps1 # Generate contrastive DPO & VLSP anchor datasets
│   ├── 02_train_models.ps1    # Train Standard DPO and OGPSA-DPO LoRA adapters
│   └── 03_run_evaluations.ps1 # Execute privacy benchmarks and evaluation metrics
├── src/                       # Core project codebase
│   ├── pii_leakage_evaluator.py # Exact-match PII entity leakage calculation
│   ├── generate_natural_dpo.py  # Curation pipeline for vdt_pii_dpo dataset
│   ├── train_defense.py       # QLoRA DPO and custom OGPSA SVD trainer
│   ├── openai_privacy_filter.py # Inference-time baseline regex + NER wrapper
│   ├── survey_natural_leakage.py# Baseline leakage benchmark on Meddies holdout
│   ├── survey_prompt_defense.py # Zero-shot instruction guardrail benchmark
│   ├── survey_filter_effectiveness.py # Baseline filter benchmark
│   ├── evaluate_defense.py    # Holdout evaluation for trained LoRA adapters
│   ├── evaluate_capability.py # ROUGE and verbosity evaluation on VLSP
│   ├── evaluate_ragas_judge.py  # LLM-as-a-Judge semantic quality scoring
│   ├── calculate_real_stats.py  # Calculates dataset properties
│   └── calculate_table2_metrics.py # Calculates privacy mitigation metrics
└── results/                   # Experimental logs and benchmark archives
    ├── benchmarks/            # JSON evaluation reports
    └── figures/               # Training dynamics diagrams
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

## 📊 Running Pipelines & Benchmarks

All datasets, training runs, and evaluation benchmarks can be executed using the automated scripts in `scripts/`.

### Step 1: Prepare Datasets
Generates the contrastive clinical preference pairs (`vdt_pii_dpo`) and formats the general domain summarization examples from VLSP:
```powershell
.\scripts\01_prepare_datasets.ps1
python src/calculate_real_stats.py
```

### Step 2: Train Privacy-Aligned Models
Fine-tunes `Qwen/Qwen2.5-1.5B-Instruct` using Standard QLoRA DPO and Orthogonal Gradient Projection (OGPSA-DPO):
```powershell
.\scripts\02_train_models.ps1
```

### Step 3: Run Privacy & Capability Benchmarks
Evaluates baseline models, heuristic filters, and trained DPO adapters on holdout clinical datasets and general domain summaries:
```powershell
.\scripts\03_run_evaluations.ps1
```

---

## 🛡️ License
This project is licensed under the MIT License. See `LICENSE` for details.
