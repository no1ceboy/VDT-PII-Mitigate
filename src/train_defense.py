"""
DPO Defense Training Script
Supports two training backends:
  1. Standard DPO (trl + QLoRA) — default, works on any single GPU
  2. OGPSA DPO (via LLaMA-Factory fork) — add --ogpsa flag for gradient projection
"""
import os
import argparse
import subprocess
import sys


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Train DPO (or OGPSA-DPO) Privacy Defense Model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ── Dataset ──────────────────────────────────────────────────────────────
    parser.add_argument("--dataset_path", type=str,
                        default="results/dpo_natural_leakage.jsonl",
                        help="Path to the DPO JSONL dataset (chosen/rejected pairs)")
    parser.add_argument("--output_dir", type=str,
                        default="results/defense_model",
                        help="Directory to save model checkpoints and final weights")

    # ── Model ─────────────────────────────────────────────────────────────────
    parser.add_argument("--model_name", type=str,
                        default="Qwen/Qwen2.5-1.5B-Instruct",
                        help="HuggingFace model ID to fine-tune")

    # ── Training hyperparameters ──────────────────────────────────────────────
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=1,
                        help="Per-device train batch size")
    parser.add_argument("--grad_accum", type=int, default=4,
                        help="Gradient accumulation steps (effective_bs = batch_size * grad_accum)")
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--beta", type=float, default=0.1,
                        help="DPO beta — KL regularisation strength")

    # ── LoRA ──────────────────────────────────────────────────────────────────
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)

    # ── Sequence length ───────────────────────────────────────────────────────
    parser.add_argument("--max_prompt_len", type=int, default=2000,
                        help="Max chars for the user prompt before truncation")
    parser.add_argument("--max_response_len", type=int, default=600,
                        help="Max chars for chosen/rejected responses")

    # ── Logging & Validation ──────────────────────────────────────────────────
    parser.add_argument("--run_name", type=str, default="vdt-pii-defense-dpo")
    parser.add_argument("--report_to", type=str, default="none",
                        choices=["none", "wandb", "tensorboard"],
                        help="Where to log training metrics")
    parser.add_argument("--val_samples", type=int, default=10,
                        help="Number of preference pairs to hold out for validation loss/accuracy logging")

    # ── OGPSA mode ────────────────────────────────────────────────────────────
    parser.add_argument("--ogpsa", action="store_true",
                        help="Use OGPSA (Orthogonal Gradient Projection) instead of vanilla DPO. "
                             "Requires the OGPSA repo (github.com/SunGL001/OGPSA) installed.")
    parser.add_argument("--ogpsa_repo", type=str, default="./OGPSA",
                        help="Path to the cloned SunGL001/OGPSA repository root")
    parser.add_argument("--base_dataset", type=str, default="vlsp_summarization_capability",
                        help="OGPSA: capability dataset name registered in dataset_info.json "
                             "(protects summarisation skill from being degraded)")
    parser.add_argument("--base_num_samples", type=int, default=200,
                        help="OGPSA: number of samples to use from --base_dataset")
    parser.add_argument("--base_num_steps", type=int, default=5,
                        help="OGPSA: steps used to estimate the capability gradient subspace")
    parser.add_argument("--deepspeed", type=str, default=None,
                        help="OGPSA: path to DeepSpeed config JSON (e.g. ds_z2_config.json). "
                             "Omit for single-GPU runs.")

    return parser


# ──────────────────────────────────────────────────────────────────────────────
# Backend 1 – Standard trl DPO (vanilla QLoRA)
# ──────────────────────────────────────────────────────────────────────────────

def run_standard_dpo(args):
    import torch
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig
    from trl import DPOTrainer, DPOConfig

    # Disable DataParallel issues with bitsandbytes on multi-GPU hosts
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

    print(f"[DPO] Loading tokenizer: {args.model_name}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    tokenizer.pad_token = tokenizer.eos_token

    print(f"[DPO] Loading dataset: {args.dataset_path}")
    dataset = load_dataset("json", data_files=args.dataset_path, split="train")

    # ── Validation ────────────────────────────────────────────────────────────
    required = {"prompt", "chosen", "rejected"}
    missing = required - set(dataset.column_names)
    if missing:
        raise ValueError(
            f"Dataset is missing required columns: {missing}. "
            f"Found: {dataset.column_names}. "
            "Make sure you are using results/dpo_natural_leakage.jsonl "
            "(not the old dpo_dataset.jsonl)."
        )

    # Hold out val_samples for evaluation (matching OGPSA logic)
    if args.val_samples > 0 and args.val_samples < len(dataset):
        split = dataset.train_test_split(test_size=args.val_samples, seed=42)
        train_dataset, eval_dataset = split["train"], split["test"]
    else:
        train_dataset, eval_dataset = dataset, None

    # ── Format ───────────────────────────────────────────────────────────────
    def format_row(row):
        prompt_messages = row["prompt"]

        # Truncate long documents — keep front + back for context
        user_content = prompt_messages[1]["content"]
        half = args.max_prompt_len // 2
        if len(user_content) > args.max_prompt_len:
            prompt_messages[1]["content"] = (
                user_content[:half] + "\n...[TRUNCATED]...\n" + user_content[-half:]
            )

        prompt_str = tokenizer.apply_chat_template(
            prompt_messages, tokenize=False, add_generation_prompt=True
        )
        # Cap response length so we don't OOM on the reference model copy
        chosen_str  = row["chosen"][0]["content"][:args.max_response_len]  + tokenizer.eos_token
        rejected_str = row["rejected"][0]["content"][:args.max_response_len] + tokenizer.eos_token
        return {"prompt": prompt_str, "chosen": chosen_str, "rejected": rejected_str}

    print("[DPO] Formatting dataset...")
    train_dataset = train_dataset.map(format_row, remove_columns=train_dataset.column_names)
    if eval_dataset is not None:
        eval_dataset = eval_dataset.map(format_row, remove_columns=eval_dataset.column_names)

    # ── Model (QLoRA 4-bit) ───────────────────────────────────────────────────
    print("[DPO] Loading model with 4-bit QLoRA…")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        # Use bfloat16 compute dtype on 30/40-series GPUs (Ampere+), float16 on older
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True,   # extra ~0.4-bit savings
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        quantization_config=bnb_config,
        device_map={"": 0},
        attn_implementation="flash_attention_2" if _flash_attn_available() else "eager",
    )
    model.config.use_cache = False  # required for gradient checkpointing

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        # Include gate_proj / up_proj / down_proj for better coverage on Qwen MLP
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )

    # ── Training config ───────────────────────────────────────────────────────
    use_bf16 = torch.cuda.is_bf16_supported()
    training_args = DPOConfig(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        logging_steps=5,
        eval_strategy="steps" if eval_dataset is not None else "no",
        eval_steps=20 if eval_dataset is not None else None,
        save_strategy="epoch",
        # paged_adamw_8bit uses far less VRAM on 3090/4090 than 32bit
        optim="paged_adamw_8bit",
        bf16=use_bf16,
        fp16=not use_bf16,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=args.report_to,
        run_name=args.run_name,
        beta=args.beta,
        # Prevent the trainer from re-tokenising already-formatted strings
        precompute_ref_log_probs=False,
        max_length=2048,
        max_prompt_length=1600,
    )

    trainer = DPOTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    print("[DPO] Starting training…")
    trainer.train()

    final_path = os.path.join(args.output_dir, "final")
    print(f"[DPO] Saving final model to {final_path}")
    trainer.save_model(final_path)
    tokenizer.save_pretrained(final_path)
    print("[DPO] Done!")


def _flash_attn_available() -> bool:
    try:
        import flash_attn  # noqa: F401
        return True
    except ImportError:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Backend 2 – OGPSA via LLaMA-Factory CLI (dpo_pg stage)
# ──────────────────────────────────────────────────────────────────────────────

def run_ogpsa_dpo(args):
    """
    Delegates training to llamafactory-cli with stage=dpo_pg.

    Pre-requisites (run once):
        git clone https://github.com/SunGL001/OGPSA.git
        pip install -e ./OGPSA

    Your DPO dataset (dpo_natural_leakage.jsonl) must be registered in
    OGPSA/data/dataset_info.json as 'vdt_pii_dpo' (see comment below).

    Your capability dataset (e.g. VLSP summaries) must be registered as
    the name you pass to --base_dataset.
    """
    ogpsa_root = os.path.abspath(args.ogpsa_repo)
    llamafactory_cli = os.path.join(ogpsa_root, ".venv", "Scripts", "llamafactory-cli")
    # Fallback: check system PATH
    if not os.path.exists(llamafactory_cli):
        llamafactory_cli = "llamafactory-cli"

    # Resolve absolute output dir before changing cwd
    if args.output_dir == "results/defense_model":
        output_dir = os.path.abspath("results/defense_model_ogpsa")
    else:
        output_dir = os.path.abspath(args.output_dir)

    print("[OGPSA] Automatically preparing and formatting datasets for LLaMA-Factory...")
    try:
        from src.prepare_ogpsa_data import main as prepare_main
        import sys
        old_argv = sys.argv
        sys.argv = [
            "prepare_ogpsa_data.py", 
            "--dpo_jsonl", args.dataset_path, 
            "--patch_repo", ogpsa_root, 
            "--vlsp_limit", str(args.base_num_samples)
        ]
        prepare_main()
        sys.argv = old_argv
        print("[OGPSA] Dataset preparation and OGPSA repository patching succeeded!\n")
    except Exception as e:
        print(f"[WARN] Automatic dataset preparation failed: {e}. Assuming datasets are already prepared in {ogpsa_root}/data/...")

    print("[OGPSA] Building llamafactory-cli command…")
    use_bf16 = True  # 3090/4090 both support bf16

    cmd = [
        llamafactory_cli, "train",
        "--stage",                    "dpo_pg",
        "--do_train",                 "True",
        "--model_name_or_path",       args.model_name,
        "--finetuning_type",          "lora",
        "--lora_rank",                str(args.lora_r),
        "--lora_alpha",               str(args.lora_alpha),
        "--lora_target",              "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
        "--template",                 "qwen",
        "--flash_attn",               "auto",
        "--dataset_dir",              os.path.join(ogpsa_root, "data"),
        "--dataset",                  "vdt_pii_dpo",          # register your JSONL here
        "--val_size",                 str(round(args.val_samples / 489.0, 5)) if args.val_samples > 0 else "0",
        "--eval_strategy",            "steps" if args.val_samples > 0 else "no",
        "--eval_steps",               "20",
        "--do_eval",                  "True" if args.val_samples > 0 else "False",
        "--cutoff_len",               "2048",
        "--learning_rate",            str(args.lr),
        "--num_train_epochs",         str(args.epochs),
        "--per_device_train_batch_size", str(args.batch_size),
        "--gradient_accumulation_steps", str(args.grad_accum),
        "--lr_scheduler_type",        "cosine",
        "--max_grad_norm",            "1.0",
        "--logging_steps",            "5",
        "--save_strategy",            "epoch",
        "--save_only_model",          "True",
        "--warmup_steps",             "0",
        "--report_to",                args.report_to,
        "--output_dir",               output_dir,
        "--bf16",                     str(use_bf16),
        "--plot_loss",                "True",
        "--trust_remote_code",        "True",
        "--optim",                    "paged_adamw_8bit",
        "--pref_beta",                str(args.beta),
        "--pref_loss",                "sigmoid",
        # ── OGPSA-specific projection arguments ──────────────────────────────
        "--base_dataset",             args.base_dataset,
        "--base_num_samples",         str(args.base_num_samples),
        "--base_num_steps",           str(args.base_num_steps),
        "--base_method",              "orthogonal_projection",
        "--base_threshold",           "0",
    ]

    if args.deepspeed:
        cmd += ["--deepspeed", os.path.abspath(args.deepspeed)]

    print("\n[OGPSA] Command:\n  " + " \\\n    ".join(cmd) + "\n")
    print(
        "[OGPSA] NOTE: Before running, register your dataset in:\n"
        f"  {ogpsa_root}/data/dataset_info.json\n"
        "  Add entry 'vdt_pii_dpo' pointing to your dpo_natural_leakage.jsonl.\n"
        "  Also register your capability dataset as '{}'.\n".format(args.base_dataset)
    )

    # Run from the OGPSA repo root so llamafactory-cli finds its src modules
    result = subprocess.run(cmd, cwd=ogpsa_root)
    if result.returncode != 0:
        print("[OGPSA] Training failed. Check the output above for errors.")
        sys.exit(result.returncode)

    print(f"[OGPSA] Training complete. Checkpoints saved to {output_dir}")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.ogpsa:
        print("=" * 60)
        print("  Training backend: OGPSA-DPO (LLaMA-Factory dpo_pg)")
        print("=" * 60)
        run_ogpsa_dpo(args)
    else:
        print("=" * 60)
        print("  Training backend: Standard DPO (trl + QLoRA)")
        print("=" * 60)
        run_standard_dpo(args)


if __name__ == "__main__":
    main()
