"""
GRPO Defense Training Script

Trains a privacy-preserving summarization model using Group Relative Policy Optimization (GRPO).
This uses custom reward functions to heavily penalize PII leakage while rewarding formatting and length.
"""

import os
import argparse
import sys
import re

import torch
from datasets import Dataset, load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig

try:
    from trl import GRPOTrainer, GRPOConfig
except ImportError:
    print("[ERROR] `trl` is either not installed or too old. GRPO requires trl >= 0.15.0.")
    print("Please run: pip install trl>=0.15.0")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Reward Functions
# ──────────────────────────────────────────────────────────────────────────────

def privacy_reward_func(completions, gold_pii_flat, **kwargs):
    """
    Penalizes the model heavily for leaking PII.
    Reward = 0.0 if 0 leaks. -5.0 for each leaked item.
    (We don't reward safe behavior, we only punish unsafe behavior to prevent reward hacking).
    """
    rewards = []
    for comp, pii_list in zip(completions, gold_pii_flat):
        gen_text = comp[0]["content"] if isinstance(comp, list) else str(comp)
        
        if not pii_list or str(pii_list).lower() == "nan":
            rewards.append(0.0)
            continue
            
        leak_count = 0
        for pii_item in pii_list:
            item_str = str(pii_item).strip()
            if not item_str or len(item_str) < 3:
                continue
                
            escaped_item = re.escape(item_str)
            pattern = re.compile(rf"(?:\b|\s){escaped_item}(?:\b|\s|[.,!?;:])", re.IGNORECASE)
            
            if pattern.search(gen_text) or item_str.lower() in gen_text.lower():
                leak_count += 1
                
        if leak_count == 0:
            rewards.append(5.0)
        else:
            rewards.append(-5.0 * leak_count)
            
    return rewards


def format_reward_func(completions, **kwargs):
    """
    Small reward for outputting valid Markdown structure.
    Scaled down to prevent it from overpowering the KL penalty.
    """
    rewards = []
    for comp in completions:
        gen_text = comp[0]["content"] if isinstance(comp, list) else str(comp)
        
        score = 0.0
        if re.search(r"^\s*[-*]\s+", gen_text, re.MULTILINE):
            score += 0.1
        if re.search(r"^\s*#+\s+", gen_text, re.MULTILINE) or re.search(r"\*\*(.+?)\*\*:", gen_text):
            score += 0.1
            
        rewards.append(score)
    return rewards


def length_reward_func(completions, **kwargs):
    """
    Penalizes extremely short summaries.
    """
    rewards = []
    for comp in completions:
        gen_text = comp[0]["content"] if isinstance(comp, list) else str(comp)
        
        char_len = len(gen_text.strip())
        if char_len < 50:
            rewards.append(-1.0)
        else:
            rewards.append(0.0)
            
    return rewards


def refusal_reward_func(completions, **kwargs):
    """
    Penalizes the model heavily if it refuses to summarize or adds safety preambles.
    """
    rewards = []
    refusal_patterns = [
        r"tôi không thể",
        r"xin lỗi",
        r"không được phép",
        r"từ chối",
        r"chứa thông tin cá nhân",
        r"chứa thông tin nhạy cảm",
        r"bảo mật thông tin"
    ]
    pattern = re.compile("|".join(refusal_patterns), re.IGNORECASE)
    
    for comp in completions:
        gen_text = comp[0]["content"] if isinstance(comp, list) else str(comp)
        
        if pattern.search(gen_text):
            rewards.append(-5.0)
        else:
            rewards.append(0.0)
            
    return rewards

# ──────────────────────────────────────────────────────────────────────────────
# Data Preparation
# ──────────────────────────────────────────────────────────────────────────────

def prepare_dataset(model_name: str, split="train", limit=100, dataset_path=None):
    """
    Loads Meddies/meddies-pii and formats it for GRPO.
    GRPO expects a 'prompt' column (list of dicts) and we inject 'gold_pii_flat'.
    """
    if dataset_path:
        print(f"[GRPO] Loading dataset from local file: {dataset_path}")
        ds = load_dataset("json", data_files=dataset_path, split=split)
    else:
        print(f"[GRPO] Loading Meddies/meddies-pii ({split})...")
        ds = load_dataset("Meddies/meddies-pii", "vietnamese", split=split)
    
    if limit > 0:
        ds = ds.select(range(min(limit, len(ds))))
        
    system_prompt = "Bạn là một trợ lý AI chuyên tóm tắt văn bản y tế tiếng Việt. Lược bỏ hoàn toàn các thông tin cá nhân (PII) như tên, ngày sinh, địa chỉ, số điện thoại... hoặc thay bằng các từ ngữ chung chung (ví dụ: 'bệnh nhân', 'người nhà'). Chỉ đưa ra bản tóm tắt, tuyệt đối không giải thích hay mở bài."
    user_prompt_template = "Hãy tóm tắt tài liệu y tế sau đây:\n\n---\n{document}\n---"
    
    formatted_data = {
        "prompt": [],
        "gold_pii_flat": []
    }
    
    import json
    for row in ds:
        doc = row.get("raw", "")
        prompt = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt_template.format(document=doc)}
        ]
        
        formatted_data["prompt"].append(prompt)
        
        # Flatten PII
        flat_pii = []
        if row.get("label"):
            try:
                gold_dict = json.loads(row["label"]) if isinstance(row["label"], str) else row["label"]
                for pii_list in gold_dict.values():
                    if isinstance(pii_list, list):
                        flat_pii.extend(pii_list)
            except Exception:
                pass
        formatted_data["gold_pii_flat"].append(flat_pii)
        
    return Dataset.from_dict(formatted_data)


# ──────────────────────────────────────────────────────────────────────────────
# Main Trainer Loop
# ──────────────────────────────────────────────────────────────────────────────

def main():
    import os
    # Disable strict vLLM memory profiling assertion so it doesn't crash if other processes fluctuate GPU memory
    os.environ["VLLM_TEST_MEMORY_PROFILE"] = "0"
    
    parser = argparse.ArgumentParser(description="Train GRPO Privacy Defense Model")
    parser.add_argument("--model_name", type=str, default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--output_dir", type=str, default="results/grpo_defense_model")
    parser.add_argument("--finetuning_type", type=str, default="qlora", choices=["qlora", "lora", "fft"], help="Type of finetuning: qlora (4-bit), lora (16-bit), or fft (Full Fine-Tuning)")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=2, help="Per device generation batch size")
    parser.add_argument("--grad_accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--num_generations", type=int, default=4, help="Number of generations (G) per prompt")
    parser.add_argument("--max_prompt_length", type=int, default=1024)
    parser.add_argument("--max_completion_length", type=int, default=512)
    parser.add_argument("--limit", type=int, default=200, help="Limit dataset size for fast testing")
    parser.add_argument("--use_vllm", action="store_true", help="Use vLLM for fast generation (requires vllm installed)")
    parser.add_argument("--report_to", type=str, default="none", choices=["none", "wandb", "tensorboard"], help="Where to log training metrics")
    parser.add_argument("--dataset_path", type=str, default=None, help="Path to local JSONL dataset (if None, downloads from HF)")
    args = parser.parse_args()

    # 1. Dataset
    train_dataset = prepare_dataset(args.model_name, split="train", limit=args.limit, dataset_path=args.dataset_path)
    
    # 2. Model & LoRA Config
    print(f"[GRPO] Loading model: {args.model_name} with {args.finetuning_type}")
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig
    import torch
    
    model_kwargs = {"device_map": "auto", "torch_dtype": torch.bfloat16}
    peft_config = None
    
    if args.finetuning_type == "qlora":
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        
    if args.finetuning_type in ["qlora", "lora"]:
        peft_config = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj", "gate_proj"],
            task_type="CAUSAL_LM",
        )
        
    model = AutoModelForCausalLM.from_pretrained(args.model_name, **model_kwargs)
    
    # 3. GRPO Config
    import inspect
    config_kwargs = {
        "output_dir": args.output_dir,
        "learning_rate": args.lr,
        "per_device_train_batch_size": args.batch_size,
        "gradient_accumulation_steps": args.grad_accum,
        "num_train_epochs": args.epochs,
        "num_generations": args.num_generations,
        "report_to": args.report_to,
        "logging_steps": 1,
        "use_vllm": args.use_vllm,
        "save_strategy": "epoch",
        "bf16": True,
        "beta": 0.01,  # Loosened KL penalty to allow alignment
    }
    
    if args.use_vllm:
        # Capping at 0.8 guarantees vLLM + PyTorch + your friend's process never exceeds 80% of the B200
        config_kwargs["vllm_gpu_memory_utilization"] = 0.25
    
    config_params = inspect.signature(GRPOConfig.__init__).parameters
    if "max_prompt_length" in config_params:
        config_kwargs["max_prompt_length"] = args.max_prompt_length
    if "max_completion_length" in config_params:
        config_kwargs["max_completion_length"] = args.max_completion_length
        
    training_args = GRPOConfig(**config_kwargs)

    # 4. Initialize Trainer
    trainer_kwargs = {
        "model": model,
        "reward_funcs": [privacy_reward_func, format_reward_func, length_reward_func, refusal_reward_func],
        "args": training_args,
        "train_dataset": train_dataset,
    }
    
    if peft_config is not None:
        trainer_kwargs["peft_config"] = peft_config
    
    trainer_params = inspect.signature(GRPOTrainer.__init__).parameters
    if "max_prompt_length" in trainer_params:
        trainer_kwargs["max_prompt_length"] = args.max_prompt_length
    if "max_completion_length" in trainer_params:
        trainer_kwargs["max_completion_length"] = args.max_completion_length
        
    trainer = GRPOTrainer(**trainer_kwargs)

    print("[GRPO] Starting training...")
    trainer.train()
    
    print(f"[GRPO] Saving final adapter to {args.output_dir}")
    trainer.save_model(args.output_dir)

if __name__ == "__main__":
    main()
