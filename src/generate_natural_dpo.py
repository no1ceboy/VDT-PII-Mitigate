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
from src.pii_leakage_evaluator import PIILeakageEvaluator


def load_local_meddies_documents(dataset_path):
    """Load the exact local Meddies JSONL used by the leakage survey."""
    from src.data_loader import Document

    documents = {}
    with open(dataset_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            row = json.loads(line)
            gold_pii = row.get("label", {})
            if isinstance(gold_pii, str):
                try:
                    gold_pii = json.loads(gold_pii)
                except json.JSONDecodeError:
                    gold_pii = {}

            gold_pii_flat = []
            for values in gold_pii.values():
                if isinstance(values, list):
                    gold_pii_flat.extend(values)

            documents[f"local_{idx}"] = Document(
                id=f"local_{idx}",
                source_dataset="meddies_local",
                domain="medical",
                document=row.get("raw", ""),
                reference_summary="Tóm tắt tài liệu y khoa.",
                metadata={
                    "gold_pii": gold_pii,
                    "gold_pii_flat": gold_pii_flat,
                    "document_type": row.get("document_type", "unknown"),
                    "source_index": idx,
                },
            )
    return documents


def metadata_redact(text, document):
    """Fallback redaction using the source row's annotated PII entities."""
    chosen_text = text
    gold_pii_flat = document.metadata.get("gold_pii_flat", [])
    gold_pii = document.metadata.get("gold_pii", {})

    for pii_item in sorted(set(gold_pii_flat), key=lambda value: len(str(value)), reverse=True):
        pii_item = str(pii_item).strip()
        if len(pii_item) < 3:
            continue

        entity_type = "REDACTED"
        for etype, items in gold_pii.items():
            if isinstance(items, list) and any(pii_item.lower() == str(item).lower() for item in items):
                entity_type = str(etype).upper()
                break

        chosen_text = re.sub(
            re.escape(pii_item),
            f"<{entity_type}>",
            chosen_text,
            flags=re.IGNORECASE,
        )
    return chosen_text

def main():
    parser = argparse.ArgumentParser(description="Generate DPO pairs from natural leakage surveys")
    
    # Default: use the combined survey results
    default_files = ["results/natural_leakage_stats_combined.json"]
            
    parser.add_argument("--results_files", nargs="+", default=default_files, help="Path(s) to natural leakage survey JSON files")
    parser.add_argument("--output_file", type=str, default="results/dpo_natural_leakage.jsonl", help="Path to save output DPO JSONL")
    parser.add_argument("--model_name", type=str, default="Qwen 1.5B Local", help="Model name to filter leaked responses for")
    parser.add_argument("--dataset_path", type=str, default=None, help="Local Meddies JSONL used for the survey, e.g. datasets/meddies_full_train.jsonl")
    parser.add_argument("--filter_type", choices=["metadata", "meddies", "openai"], default="metadata", help="Redactor for chosen responses")
    parser.add_argument("--filter_model_path", type=str, default=None, help="Local Meddies or OPF model/checkpoint path")
    parser.add_argument("--filter_device", type=str, default="cpu", help="Device for the redaction filter")
    parser.add_argument("--keep_leaky_chosen", action="store_true", help="Keep pairs when redaction still leaks PII (not recommended)")
    args = parser.parse_args()
    
    results_files = args.results_files
    output_file = args.output_file
    
    if not results_files:
        print("Error: No survey results files found. Run survey_natural_leakage.py first.")
        return
        
    detailed_results = []
    seen_results = set()
    
    for rfile in results_files:
        if not os.path.exists(rfile):
            print(f"[WARN] File not found: {rfile}, skipping...")
            continue
        print(f"Reading {rfile}...")
        with open(rfile, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("detailed_results", []):
                did = item.get("doc_id")
                model_id = item.get("model", "unknown")
                # Deduplicate repeated runs, but preserve different model
                # responses for the same source document.
                result_key = (did, model_id)
                if did and result_key not in seen_results:
                    seen_results.add(result_key)
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
    if args.dataset_path:
        print(f"Loading source Meddies JSONL: {args.dataset_path}")
        doc_map = load_local_meddies_documents(args.dataset_path)
    else:
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
    
    # Initialize the selected redactor. Metadata redaction needs no extra model.
    defense = None
    if args.filter_type == "meddies":
        if not args.filter_model_path:
            raise ValueError("--filter_model_path is required when --filter_type meddies")
        from src.meddies_privacy_filter import MeddiesPrivacyFilter
        defense = MeddiesPrivacyFilter(model_path=args.filter_model_path, device=args.filter_device)
    elif args.filter_type == "openai":
        defense = PrivacyFilterDefense(model_path=args.filter_model_path, device=args.filter_device)
    
    # Load system prompt config
    config_path = "configs/attack_config.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    else:
        config = {}
    system_prompt = config.get("system_prompt", "Bạn là một trợ lý AI chuyên tóm tắt văn bản tiếng Việt. Hãy tóm tắt nội dung tài liệu được cung cấp một cách ngắn gọn, chính xác và khách quan.")
    user_prompt_template = "Hãy tóm tắt tài liệu sau đây:\n\n---\n{document}\n---"
    
    evaluator = PIILeakageEvaluator()
    dpo_pairs = []
    skipped_unclean = 0
    
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
        chosen_text = rejected_text
        if defense is not None:
            if hasattr(defense, "runtime") and defense.runtime is not None:
                chosen_text = defense.redact(rejected_text)
            elif hasattr(defense, "extractor") and defense.extractor is not None:
                chosen_text = defense.redact(rejected_text)

        # Always use metadata fallback if a model redactor is unavailable or misses
        # an annotated entity. Do not train on a supposedly preferred answer that
        # still contains the same PII leak.
        chosen_check = evaluator.evaluate(
            attacked_summary=chosen_text,
            gold_pii_flat=original_doc.metadata.get("gold_pii_flat", []),
        )
        if chosen_check.attack_success:
            chosen_text = metadata_redact(chosen_text, original_doc)
            chosen_check = evaluator.evaluate(
                attacked_summary=chosen_text,
                gold_pii_flat=original_doc.metadata.get("gold_pii_flat", []),
            )

        if chosen_check.attack_success and not args.keep_leaky_chosen:
            skipped_unclean += 1
            continue
        
        # Add to DPO dataset
        dpo_pairs.append({
            "prompt": prompt_messages,
            "chosen": [{"role": "assistant", "content": chosen_text}],
            "rejected": [{"role": "assistant", "content": rejected_text}],
            "metadata": {
                "source": "natural_leakage_survey",
                "doc_id": doc_id,
                "model_that_failed": result["model"],
                "source_dataset": original_doc.source_dataset,
                "source_index": original_doc.metadata.get("source_index"),
                "filter_type": args.filter_type,
            }
        })
        
    # Save the dataset
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in dpo_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            
    print("\n" + "="*50)
    print(f"Successfully created combined DPO dataset: {output_file}")
    print(f"Total DPO Pairs generated: {len(dpo_pairs)}")
    print(f"Skipped pairs whose chosen response still leaked PII: {skipped_unclean}")
    print("="*50)
    print("Next step: Upload this file to Kaggle and run your DPO training script!")

if __name__ == "__main__":
    main()
