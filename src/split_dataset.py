import os
import json
import random
import argparse

def main():
    parser = argparse.ArgumentParser(description="Split a JSONL dataset into train, val, and test sets.")
    parser.add_argument("--input_file", type=str, required=True, help="Path to the input JSONL file")
    parser.add_argument("--train_ratio", type=float, default=0.90, help="Proportion of data for training (default: 0.90)")
    parser.add_argument("--val_ratio", type=float, default=0.05, help="Proportion of data for validation (default: 0.05)")
    parser.add_argument("--test_ratio", type=float, default=0.05, help="Proportion of data for testing (default: 0.05)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for shuffling")
    args = parser.parse_args()

    # Validate ratios
    total = args.train_ratio + args.val_ratio + args.test_ratio
    if not (0.99 <= total <= 1.01):
        print(f"[ERROR] Ratios must sum to 1.0 (currently sum to {total})")
        return

    if not os.path.exists(args.input_file):
        print(f"[ERROR] Input file not found: {args.input_file}")
        return

    print(f"Reading data from {args.input_file}...")
    data = []
    with open(args.input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(line)

    print(f"Total documents loaded: {len(data)}")
    
    # Shuffle data
    print(f"Shuffling data with seed {args.seed}...")
    random.seed(args.seed)
    random.shuffle(data)

    # Calculate splits
    n_total = len(data)
    n_train = int(n_total * args.train_ratio)
    n_val = int(n_total * args.val_ratio)
    # Give the remainder to test
    
    train_data = data[:n_train]
    val_data = data[n_train:n_train+n_val]
    test_data = data[n_train+n_val:]

    # Construct output filenames
    base, ext = os.path.splitext(args.input_file)
    train_file = f"{base}_train{ext}"
    val_file = f"{base}_val{ext}"
    test_file = f"{base}_test{ext}"

    # Write splits
    print("Writing splits...")
    with open(train_file, "w", encoding="utf-8") as f:
        f.writelines(train_data)
    print(f" -> Train set: {len(train_data)} documents ({train_file})")

    with open(val_file, "w", encoding="utf-8") as f:
        f.writelines(val_data)
    print(f" -> Val set: {len(val_data)} documents ({val_file})")

    with open(test_file, "w", encoding="utf-8") as f:
        f.writelines(test_data)
    print(f" -> Test set: {len(test_data)} documents ({test_file})")

    print("\n[SUCCESS] Dataset splitting complete!")

if __name__ == "__main__":
    main()
