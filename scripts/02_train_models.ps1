# Step 2: Train Privacy-Aligned Models (Standard QLoRA DPO vs. OGPSA-DPO)
Write-Host "=== STEP 2: MODEL TRAINING ===" -ForegroundColor Cyan

# Train Standard QLoRA DPO model
Write-Host "`n[1/2] Training Standard QLoRA DPO Model..." -ForegroundColor Yellow
python src/train_defense.py --model_name "Qwen/Qwen2.5-1.5B-Instruct" --dataset_path "results/dpo_natural_leakage.jsonl" --output_dir "results/defense_model_standard" --epochs 3 --batch_size 1 --grad_accum 8 --lr 5e-5 --beta 0.2

# Train Capability-Protected OGPSA-DPO model
Write-Host "`n[2/2] Training OGPSA-DPO Model with Orthogonal Gradient Projection..." -ForegroundColor Yellow
python src/train_defense.py --ogpsa --model_name "Qwen/Qwen2.5-1.5B-Instruct" --dataset_path "results/dpo_natural_leakage.jsonl" --base_dataset "vlsp_summarization_capability" --output_dir "results/defense_model_ogpsa" --epochs 3 --batch_size 1 --grad_accum 8 --lr 5e-5 --beta 0.2

Write-Host "`n[Bonus] Plotting training dynamics and margin expansion curves..." -ForegroundColor Yellow
python src/plot_training_curves.py

Write-Host "`n=== Model training and curve generation completed successfully! ===" -ForegroundColor Green
