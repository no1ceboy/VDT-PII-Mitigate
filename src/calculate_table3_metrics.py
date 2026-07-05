import json

def main():
    with open("results/capability_results.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print("="*90)
    print(f"{'Defense Mechanism':<28} | {'ROUGE-1 F1':<12} | {'ROUGE-2 F1':<12} | {'ROUGE-L F1':<12} | {'Length Ratio':<12}")
    print("-" * 90)
    
    order = [
        ("Base_Model", "1. Undefended Base Model"),
        ("Baseline_Filter", "3. Baseline Privacy Filter"),
        ("Standard_DPO", "4. Standard QLoRA DPO"),
        ("OGPSA_DPO", "5. OGPSA QLoRA DPO")
    ]
    
    for key, label in order:
        items = data.get(key, [])
        if not items:
            print(f"{label:<28} | {'--':<12} | {'--':<12} | {'--':<12} | {'--':<12}")
            continue
        r1 = sum(x["rouge1"] for x in items) / len(items)
        r2 = sum(x["rouge2"] for x in items) / len(items)
        rL = sum(x["rougeL"] for x in items) / len(items)
        lr = sum(x["len_ratio"] for x in items) / len(items)
        print(f"{label:<28} | {r1:>10.2f} | {r2:>10.2f} | {rL:>10.2f} | {lr:>10.2f}")
    print("="*90)

if __name__ == "__main__":
    main()
