# OGPSA Patches

This directory contains the modified files from [SunGL001/OGPSA](https://github.com/SunGL001/OGPSA)
applied for VDT-PII-Defense compatibility.

## Setup

```bash
git clone https://github.com/SunGL001/OGPSA.git OGPSA
# Apply patches
cp -r ogpsa_patches/data/* OGPSA/data/
cp -r ogpsa_patches/src/* OGPSA/src/
pip install -e ./OGPSA
```

## Changes

| File | Change |
|------|--------|
| `data/dataset_info.json` | Added `vdt_pii_dpo` and `vlsp_summarization_capability` dataset registrations |
| `src/llamafactory/train/dpo_pg/workflow.py` | DPO workflow with orthogonal gradient projection |
| `src/llamafactory/extras/misc.py` | Compatibility fix |
| `src/llamafactory/model/model_utils/*.py` | Qwen2.5 compatibility patches |

## Training

```bash
python src/train_defense.py \
  --ogpsa --ogpsa_repo "./OGPSA" \
  --model_name "Qwen/Qwen2.5-1.5B-Instruct" \
  --dataset_path "results/dpo_natural_leakage.jsonl" \
  --base_dataset "vlsp_summarization_capability" \
  --epochs 3 --batch_size 1 --grad_accum 8 --lr 5e-5 --beta 0.2
```
