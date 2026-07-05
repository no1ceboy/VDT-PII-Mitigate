"""
Generate Natural Leakage DPO Dataset
This script reads the natural leakage survey results (can combine multiple runs!),
applies the Privacy Filter (or metadata rule-based fallback) to redact leaked PII, 
and creates "Perfect DPO Pairs".
Chosen: Redacted summary
Rejected: The naturally generated summary (with leaked PII)
"""

import json
import os
import yaml
import argparse
import re
from tqdm import tqdm

from src.data_loader import DataLoader
from src.openai_privacy_filter import PrivacyFilterDefense

def main():
    parser = argparse.ArgumentParser(description="Generate DPO pairs from natural leakage surveys")
    
    # Default: combine both the initial 100-doc survey and the new 400-doc survey
    default_files = []
    for f in ["results/natural_leakage_stats.json", "results/natural_leakage_stats_400.json"]:
        if os.path.exists(f):
            default_files.append(f)
            
    parser.add_argument("--results_files", nargs="+", default=default_files, help="Path(s) to natural leakage survey JSON files")
    parser.add_argument("--output_file", type=str, default="results/dpo_natural_leakage.jsonl", help="Path to save output DPO JSONL")
    parser.add_argument("--model_name", type=str, default="Qwen 1.5B Local", help="Model name to filter leaked responses for")
    args = parser.parse_args()
    
    results_files = args.results_files
    output_file = args.output_file
    
    if not results_files:
        print("Error: No survey results files found. Run survey_natural_leakage.py first.")
        return
        
    detailed_results = []
    seen_doc_ids = set()
    
    for rfile in results_files:
        if not os.path.exists(rfile):
            print(f"[WARN] File not found: {rfile}, skipping...")
            continue
        print(f"Reading {rfile}...")
        with open(rfile, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("detailed_results", []):
                did = item.get("doc_id")
                # Deduplicate if the same doc_id was run in multiple surveys
                if did and did not in seen_doc_ids:
                    seen_doc_ids.add(did)
                    detailed_results.append(item)
                    
    # Filter for the specified model's leaked responses
    if args.model_name and args.model_name.lower() != "all":
        leaked_responses = [r for r in detailed_results if r.get("model") == args.model_name and r.get("is_leaked")]
    else:
        leaked_responses = [r for r in detailed_results if r.get("is_leaked")]
        
    print(f"Combined total: found {len(leaked_responses)} leaked responses from {args.model_name or 'all models'}.")
    
    if len(leaked_responses) == 0:
        print("No leaked responses found. Exiting.")
        return
        
    # Load original datasets to get the input document text
    print("Loading original local datasets...")
    data_loader = DataLoader("datasets")
    all_docs = data_loader.load_all(["medical"])
    doc_map = {doc.id: doc for doc in all_docs}
    
    # Check if we need Hugging Face documents
    hf_doc_ids = [r["doc_id"] for r in leaked_responses if str(r["doc_id"]).startswith("hf_")]
    if hf_doc_ids:
        print(f"Found {len(hf_doc_ids)} Hugging Face document IDs. Loading from HF...")
        try:
            from src.survey_natural_leakage import load_from_hf
            # Extract indices from IDs formatted like hf_{config}_{idx}_{uid}
            indices = []
            config_name = "vietnamese"
            for did in hf_doc_ids:
                parts = str(did).split("_")
                if len(parts) >= 3 and parts[2].isdigit():
                    indices.append(int(parts[2]))
                if len(parts) >= 2 and parts[1] != "vietnamese":
                    config_name = parts[1]
            if indices:
                min_idx = min(indices)
                max_idx = max(indices)
                limit = max_idx - min_idx + 1
                print(f"Fetching HF dataset range: offset={min_idx}, limit={limit} (config: {config_name})...")
                hf_docs = load_from_hf(dataset_name="Meddies/meddies-pii", config_name=config_name, split="train", limit=limit, offset=min_idx)
                for d in hf_docs:
                    doc_map[d.id] = d
                print(f"Successfully loaded {len(hf_docs)} documents from Hugging Face.")
        except Exception as e:
            print(f"[ERROR] Failed to load documents from Hugging Face: {e}")
    
    # Initialize the Privacy Filter (Use CPU to avoid VRAM issues since it's a small batch)
    print("Initializing Privacy Filter...")
    defense = PrivacyFilterDefense(device="cpu")
    
    # Load system prompt config
    config_path = "configs/attack_config.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    else:
        config = {}
    system_prompt = config.get("system_prompt", "Bạn là một trợ lý AI chuyên tóm tắt văn bản tiếng Việt. Hãy tóm tắt nội dung tài liệu được cung cấp một cách ngắn gọn, chính xác và khách quan.")
    user_prompt_template = "Hãy tóm tắt tài liệu sau đây:\n\n---\n{document}\n---"
    
    dpo_pairs = []
    
    print("Generating Perfect DPO Pairs...")
    for result in tqdm(leaked_responses):
        doc_id = result["doc_id"]
        if doc_id not in doc_map:
            continue
            
        original_doc = doc_map[doc_id]
        
        # 1. Format the input prompt exactly as seen by the model
        user_prompt = user_prompt_template.format(document=original_doc.document)
        prompt_messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()}
        ]
        
        # 2. The Rejected response is the natural summary that leaked PII
        rejected_text = result["generated_summary"]
        
        # 3. The Chosen response is the identical summary, but scrubbed!
        if defense.runtime is not None:
            chosen_text = defense.redact(rejected_text)
        else:
            # Fallback to metadata-based rule redaction
            chosen_text = rejected_text
            gold_pii_flat = original_doc.metadata.get("gold_pii_flat", [])
            sorted_pii = sorted(list(set(gold_pii_flat)), key=len, reverse=True)
            for pii_item in sorted_pii:
                pii_item = str(pii_item).strip()
                if not pii_item or len(pii_item) < 3:
                    continue
                escaped_item = re.escape(pii_item)
                entity_type = "REDACTED"
                gold_pii = original_doc.metadata.get("gold_pii", {})
                for etype, items in gold_pii.items():
                    if isinstance(items, list) and (pii_item in items or any(pii_item.lower() == str(it).lower() for it in items)):
                        entity_type = etype.upper()
                        break
                placeholder = f"<{entity_type}>"
                chosen_text = re.sub(escaped_item, placeholder, chosen_text, flags=re.IGNORECASE)
        
        # Add to DPO dataset
        dpo_pairs.append({
            "prompt": prompt_messages,
            "chosen": [{"role": "assistant", "content": chosen_text}],
            "rejected": [{"role": "assistant", "content": rejected_text}],
            "metadata": {
                "source": "natural_leakage_survey",
                "doc_id": doc_id,
                "model_that_failed": result["model"]
            }
        })
        
    # Save the dataset
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in dpo_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            
    print("\n" + "="*50)
    print(f"Successfully created combined DPO dataset: {output_file}")
    print(f"Total DPO Pairs generated: {len(dpo_pairs)}")
    print("="*50)
    print("Next step: Upload this file to Kaggle and run your DPO training script!")

if __name__ == "__main__":
    main()
