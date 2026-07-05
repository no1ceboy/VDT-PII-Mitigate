"""
Prepare OGPSA and LLaMA-Factory Datasets
This script converts our generated DPO pairs and raw VLSP data into standard, 
guaranteed-to-work Alpaca JSON format required by LLaMA-Factory and OGPSA.

Outputs:
  1. results/dpo_natural_leakage_alpaca.json (489 preference pairs in Alpaca format)
  2. results/vlsp_capability_200.json (200 clean VLSP summarization tasks for OGPSA capability subspace)
  3. results/ogpsa_dataset_info_snippet.json (Exact configuration block for OGPSA/data/dataset_info.json)
"""

import os
import json
import argparse
import shutil
from pathlib import Path
from src.data_loader import DataLoader

def main():
    parser = argparse.ArgumentParser(description="Prepare datasets for LLaMA-Factory / OGPSA")
    parser.add_argument("--dpo_jsonl", type=str, default="results/dpo_natural_leakage.jsonl", help="Input DPO JSONL file")
    parser.add_argument("--vlsp_limit", type=int, default=200, help="Number of VLSP summaries for capability projection")
    parser.add_argument("--output_dir", type=str, default="results", help="Directory to save converted JSON files")
    parser.add_argument("--patch_repo", type=str, default=None, help="Path to cloned OGPSA repo (e.g. ./OGPSA) to automatically install data and register in dataset_info.json")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # ---------------------------------------------------------
    # 1. Convert DPO JSONL to LLaMA-Factory Alpaca Ranking format
    # ---------------------------------------------------------
    print(f"Reading DPO dataset from {args.dpo_jsonl}...")
    if not os.path.exists(args.dpo_jsonl):
        print(f"[ERROR] DPO file {args.dpo_jsonl} not found. Please run generate_natural_dpo.py first.")
        return

    alpaca_dpo = []
    with open(args.dpo_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            
            # Extract prompt messages
            prompt_msgs = item.get("prompt", [])
            sys_msg = ""
            usr_msg = ""
            for m in prompt_msgs:
                if m["role"] == "system":
                    sys_msg = m["content"]
                elif m["role"] == "user":
                    usr_msg = m["content"]
                    
            chosen_msgs = item.get("chosen", [])
            chosen_str = chosen_msgs[0]["content"] if chosen_msgs else ""
            
            rejected_msgs = item.get("rejected", [])
            rejected_str = rejected_msgs[0]["content"] if rejected_msgs else ""
            
            alpaca_dpo.append({
                "instruction": usr_msg,
                "system": sys_msg,
                "chosen": chosen_str,
                "rejected": rejected_str
            })

    dpo_out_path = os.path.join(args.output_dir, "dpo_natural_leakage_alpaca.json")
    with open(dpo_out_path, "w", encoding="utf-8") as f:
        json.dump(alpaca_dpo, f, ensure_ascii=False, indent=2)
    print(f"-> Converted {len(alpaca_dpo)} DPO pairs to Alpaca format: {dpo_out_path}")

    # ---------------------------------------------------------
    # 2. Extract VLSP summaries for OGPSA capability dataset
    # ---------------------------------------------------------
    vlsp_out_path = os.path.join(args.output_dir, "vlsp_capability_200.json")
    if os.path.exists(vlsp_out_path):
        print(f"\n[INFO] Found pre-generated capability dataset at {vlsp_out_path}! Reusing existing file.")
    else:
        print(f"\nLoading {args.vlsp_limit} clean summaries from local VLSP dataset...")
        data_loader = DataLoader("datasets")
        vlsp_docs = data_loader._load_vlsp(limit=args.vlsp_limit)
        
        if not vlsp_docs:
            print("[WARN] No VLSP documents loaded. Falling back to medical/legal summaries for capability dataset...")
            vlsp_docs = data_loader.load_all(["legal", "medical"], limit_per_dataset=args.vlsp_limit // 2)

        alpaca_vlsp = []
        sys_prompt = "Bạn là một trợ lý AI chuyên tóm tắt văn bản tiếng Việt. Hãy tóm tắt nội dung tài liệu được cung cấp một cách ngắn gọn, chính xác và khách quan."
        for doc in vlsp_docs:
            instruction = f"Hãy tóm tắt tài liệu sau đây:\n\n---\n{doc.document}\n---"
            alpaca_vlsp.append({
                "instruction": instruction,
                "system": sys_prompt,
                "input": "",
                "output": doc.reference_summary
            })

        with open(vlsp_out_path, "w", encoding="utf-8") as f:
            json.dump(alpaca_vlsp, f, ensure_ascii=False, indent=2)
        print(f"-> Created capability dataset ({len(alpaca_vlsp)} examples): {vlsp_out_path}")

    # ---------------------------------------------------------
    # 3. Generate dataset_info.json configuration snippet
    # ---------------------------------------------------------
    dataset_info_snippet = {
        "vdt_pii_dpo": {
            "file_name": "dpo_natural_leakage_alpaca.json",
            "ranking": True,
            "columns": {
                "prompt": "instruction",
                "system": "system",
                "chosen": "chosen",
                "rejected": "rejected"
            }
        },
        "vlsp_summarization_capability": {
            "file_name": "vlsp_capability_200.json",
            "columns": {
                "prompt": "instruction",
                "system": "system",
                "query": "input",
                "response": "output"
            }
        }
    }

    snippet_path = os.path.join(args.output_dir, "ogpsa_dataset_info_snippet.json")
    with open(snippet_path, "w", encoding="utf-8") as f:
        json.dump(dataset_info_snippet, f, ensure_ascii=False, indent=2)
    print(f"\n-> Saved LLaMA-Factory dataset_info block to: {snippet_path}")

    # ---------------------------------------------------------
    # 4. Optional: Automatically patch cloned OGPSA repository
    # ---------------------------------------------------------
    if args.patch_repo:
        repo_dir = Path(args.patch_repo)
        data_dir = repo_dir / "data"
        info_file = data_dir / "dataset_info.json"
        
        if not data_dir.exists():
            print(f"[ERROR] OGPSA data dir {data_dir} does not exist.")
            return
            
        print(f"\nPatching OGPSA repository at {repo_dir}...")
        # Copy JSON files
        shutil.copy(dpo_out_path, data_dir / "dpo_natural_leakage_alpaca.json")
        shutil.copy(vlsp_out_path, data_dir / "vlsp_capability_200.json")
        print(f"-> Copied data files into {data_dir}")
        
        # Patch dataset_info.json
        if info_file.exists():
            with open(info_file, "r", encoding="utf-8") as f:
                info_data = json.load(f)
            info_data.update(dataset_info_snippet)
            with open(info_file, "w", encoding="utf-8") as f:
                json.dump(info_data, f, ensure_ascii=False, indent=2)
            print(f"-> Updated {info_file} with 'vdt_pii_dpo' and 'vlsp_summarization_capability' entries!")
        else:
            with open(info_file, "w", encoding="utf-8") as f:
                json.dump(dataset_info_snippet, f, ensure_ascii=False, indent=2)
            print(f"-> Created new {info_file}")

    print("\n" + "="*60)
    print("SUCCESS! Both DPO and VLSP Capability datasets are ready for LLaMA-Factory.")
    print("="*60)

if __name__ == "__main__":
    main()
