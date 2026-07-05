# Step 3: Run Out-of-Distribution Privacy and Capability Benchmarks
Write-Host "=== STEP 3: BENCHMARKING & EVALUATION ===" -ForegroundColor Cyan

# 1. Survey Baseline Models
Write-Host "`n[1/6] Benchmarking Undefended Base Model (Table 2 Row 1)..." -ForegroundColor Yellow
python src/survey_natural_leakage.py --limit 100 --use-hf --hf-offset 2000

Write-Host "`n[2/6] Benchmarking Zero-Shot Prompt Defense (Table 2 Row 2)..." -ForegroundColor Yellow
python src/survey_prompt_defense.py --limit 100 --use-hf --hf-offset 2000

Write-Host "`n[3/6] Benchmarking Heuristic Privacy Filter (Table 2 Row 3)..." -ForegroundColor Yellow
python src/survey_filter_effectiveness.py --limit 100 --use-hf --hf-offset 2000

# 2. Evaluate Trained DPO Models
Write-Host "`n[4/6] Evaluating Parametric DPO and OGPSA-DPO Models on Holdout Benchmark..." -ForegroundColor Yellow
python src/evaluate_defense.py --limit 100 --test_source hf --hf_offset 2000

# 3. Evaluate General Utility on VLSP
Write-Host "`n[5/6] Evaluating Capability Preservation and ROUGE on VLSP Anchor Set..." -ForegroundColor Yellow
python src/evaluate_capability.py --limit 30

# 4. Compute Final Table Stats
Write-Host "`n[6/6] Calculating Exact Metrics for Paper Tables..." -ForegroundColor Yellow
python src/calculate_real_stats.py
python src/calculate_table2_metrics.py
python src/calculate_table3_metrics.py

Write-Host "`n=== All benchmarks and evaluations completed! Check results/ for reports. ===" -ForegroundColor Green
