import json
import os
from datasets import load_dataset

def main():
    print("Downloading Meddies/meddies-pii from Hugging Face...")
    ds = load_dataset("Meddies/meddies-pii", "vietnamese", split="train")
    
    output_path = "results/grpo_dataset.jsonl"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"Saving {len(ds)} records to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        for row in ds:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    print("Done! You can now push this file to git and use it on the offline machine.")

if __name__ == "__main__":
    main()
