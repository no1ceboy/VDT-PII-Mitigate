import json
import os
import sys
from transformers import AutoTokenizer

def main():
    print("Initializing Qwen tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
    
    # ---------------------------------------------------------
    # 1. DPO Train Stats (results/dpo_natural_leakage.jsonl)
    # ---------------------------------------------------------
    dpo_path = "results/dpo_natural_leakage.jsonl"
    print(f"Loading training dataset from {dpo_path}...")
    
    train_count = 0
    total_prompt_tokens = 0
    total_chosen_tokens = 0
    total_rejected_tokens = 0
    total_pii_entities = 0
    
    pii_tags = ["<HUMAN_NAME>", "<DATE>", "<ID_NUMBER>", "<ADDRESS>", "<PHONE_NUMBER>", "<EMAIL_ADDRESS>"]
    
    with open(dpo_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            
            # Extract prompt content
            # prompt is a list of chat template dicts, raw text is in prompt[1]['content']
            prompt_content = row["prompt"][1]["content"]
            prompt_tokens = len(tokenizer.encode(prompt_content))
            
            # Extract chosen/rejected content
            chosen_content = row["chosen"][0]["content"] if isinstance(row["chosen"], list) else row["chosen"]
            rejected_content = row["rejected"][0]["content"] if isinstance(row["rejected"], list) else row["rejected"]
            
            chosen_tokens = len(tokenizer.encode(chosen_content))
            rejected_tokens = len(tokenizer.encode(rejected_content))
            
            # Count PII tags in the chosen summary (since they represent redacted entities)
            pii_count = sum(chosen_content.count(tag) for tag in pii_tags)
            
            train_count += 1
            total_prompt_tokens += prompt_tokens
            total_chosen_tokens += chosen_tokens
            total_rejected_tokens += rejected_tokens
            total_pii_entities += pii_count
            
    print(f"Loaded {train_count} DPO training pairs.")
    
    avg_prompt_tokens = total_prompt_tokens / train_count
    avg_chosen_tokens = total_chosen_tokens / train_count
    avg_rejected_tokens = total_rejected_tokens / train_count
    avg_pii_per_doc = total_pii_entities / train_count
    
    print("\n--- DPO Training Dataset Statistics (Real Numbers) ---")
    print(f"Total pairs: {train_count}")
    print(f"Average prompt tokens: {avg_prompt_tokens:.2f}")
    print(f"Average chosen tokens: {avg_chosen_tokens:.2f}")
    print(f"Average rejected tokens: {avg_rejected_tokens:.2f}")
    print(f"Average PII entities per document: {avg_pii_per_doc:.2f}")
    
    # ---------------------------------------------------------
    # 2. Holdout Eval Stats (Meddies/meddies-pii offset 2000, limit 50)
    # ---------------------------------------------------------
    print("\nLoading holdout dataset from Hugging Face Meddies/meddies-pii...")
    from datasets import load_dataset
    
    try:
        ds = load_dataset("Meddies/meddies-pii", "vietnamese", split="train")
        offset = 2000
        limit = 100
        end_idx = min(offset + limit, len(ds))
        
        eval_count = 0
        total_eval_prompt_tokens = 0
        total_eval_pii_entities = 0
        
        for idx in range(offset, end_idx):
            item = ds[idx]
            raw_doc = item.get("raw", "")
            eval_prompt_tokens = len(tokenizer.encode(raw_doc))
            
            # Parse gold PII from JSON string in 'label'
            gold_pii = {}
            if item.get("label"):
                try:
                    gold_pii = json.loads(item["label"])
                except Exception as e:
                    pass
            
            # Count flat entities
            gold_pii_flat = []
            for val in gold_pii.values():
                if isinstance(val, list):
                    gold_pii_flat.extend(val)
            
            eval_count += 1
            total_eval_prompt_tokens += eval_prompt_tokens
            total_eval_pii_entities += len(gold_pii_flat)
            
        avg_eval_prompt_tokens = total_eval_prompt_tokens / eval_count
        avg_eval_pii_per_doc = total_eval_pii_entities / eval_count
        
        print("\n--- Holdout Evaluation Dataset Statistics (Real Numbers) ---")
        print(f"Total evaluation docs: {eval_count}")
        print(f"Average eval prompt tokens: {avg_eval_prompt_tokens:.2f}")
        print(f"Average eval PII entities per document: {avg_eval_pii_per_doc:.2f}")
        
    except Exception as e:
        print(f"[ERROR] Failed to load dataset from HF: {e}")

if __name__ == '__main__':
    main()
