# Step 1: Prepare Contrastive DPO and VLSP Capability Anchor Datasets
Write-Host "=== STEP 1: DATASET PREPARATION ===" -ForegroundColor Cyan

# Create results directory if not exists
New-Item -ItemType Directory -Force -Path "results" | Out-Null

Write-Host "`n[1/3] Generating natural DPO contrastive pairs from Meddies/meddies-pii..." -ForegroundColor Yellow
python src/generate_natural_dpo.py --limit 500 --output "results/dpo_natural_leakage.jsonl"

Write-Host "`n[2/3] Formatting DPO dataset for QLoRA training..." -ForegroundColor Yellow
python src/prepare_dpo_data.py

Write-Host "`n[3/3] Preparing VLSP capability anchor dataset for OGPSA orthogonal projection..." -ForegroundColor Yellow
python src/prepare_ogpsa_data.py

Write-Host "`n=== Dataset preparation completed successfully! ===" -ForegroundColor Green
