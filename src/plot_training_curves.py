import json
import matplotlib.pyplot as plt
import os

# Define paths
STANDARD_PATH = "C:/Users/Minh/Desktop/PROJECT/VDT/results/defense_model_standard/checkpoint-165/trainer_state.json"
OGPSA_PATH = "C:/Users/Minh/Desktop/PROJECT/VDT/results/defense_model_ogpsa/trainer_state.json"
OUTPUT_DIR = "C:/Users/Minh/Desktop/PROJECT/VDT/results/figures"

def load_history(path):
    with open(path, 'r') as f:
        data = json.load(f)
    return data['log_history']

def extract_metrics(history, max_step=None):
    train_steps = []
    train_loss = []
    train_margin = []
    train_acc = []
    
    eval_steps = []
    eval_loss = []
    eval_margin = []
    eval_acc = []
    
    for log in history:
        step = log.get('step')
        if step is None:
            continue
        if max_step is not None and step > max_step:
            continue
            
        # Check if it's an evaluation step
        if 'eval_loss' in log:
            eval_steps.append(step)
            eval_loss.append(log['eval_loss'])
            eval_acc.append(log.get('eval_rewards/accuracies', 0.0))
            eval_margin.append(log.get('eval_rewards/margins', 0.0))
        else:
            # Training step
            # HuggingFace sometimes repeats step numbers or has step logs without loss
            if 'loss' in log:
                train_steps.append(step)
                train_loss.append(log['loss'])
                train_margin.append(log.get('rewards/margins', 0.0))
                train_acc.append(log.get('rewards/accuracies', 0.0))
                
    return {
        'train_steps': train_steps, 'train_loss': train_loss, 'train_margin': train_margin, 'train_acc': train_acc,
        'eval_steps': eval_steps, 'eval_loss': eval_loss, 'eval_margin': eval_margin, 'eval_acc': eval_acc
    }

def main():
    print("Loading log histories...")
    standard_history = load_history(STANDARD_PATH)
    ogpsa_history = load_history(OGPSA_PATH)
    
    print("Extracting metrics...")
    std_metrics = extract_metrics(standard_history, max_step=165)
    ogp_metrics = extract_metrics(ogpsa_history, max_step=165)
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Use clean plotting style
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.size'] = 11
    plt.rcParams['grid.alpha'] = 0.3
    
    # Color Palette: Crimson (Standard DPO) vs. Royal Blue (OGPSA-DPO)
    STD_TRAIN_COLOR = '#d63031' # Crimson Red
    STD_VAL_COLOR = '#ff7675'   # Light Coral
    OGP_TRAIN_COLOR = '#0984e3' # Royal Blue
    OGP_VAL_COLOR = '#74b9ff'   # Light Blue
    
    # -------------------------------------------------------------
    # Plot 1: Loss Comparison (Training & Validation)
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    
    # Standard DPO curves
    ax.plot(std_metrics['train_steps'], std_metrics['train_loss'], label='Standard DPO (Train)', color=STD_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax.plot(std_metrics['eval_steps'], std_metrics['eval_loss'], label='Standard DPO (Val)', color=STD_VAL_COLOR, linestyle='--', marker='o', markersize=5, linewidth=2)
    
    # OGPSA-DPO curves
    ax.plot(ogp_metrics['train_steps'], ogp_metrics['train_loss'], label='OGPSA-DPO (Train)', color=OGP_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax.plot(ogp_metrics['eval_steps'], ogp_metrics['eval_loss'], label='OGPSA-DPO (Val)', color=OGP_VAL_COLOR, linestyle='--', marker='s', markersize=5, linewidth=2)
    
    ax.set_xlabel("Steps", fontweight='semibold')
    ax.set_ylabel("Loss", fontweight='semibold')
    ax.grid(True)
    ax.legend(frameon=True, facecolor='white', framealpha=0.9)
    ax.set_yscale('log')
    
    plt.tight_layout()
    loss_fig_path = os.path.join(OUTPUT_DIR, "training_loss_comparison.png")
    plt.savefig(loss_fig_path, dpi=300)
    plt.close()
    print(f"Saved loss plot to: {loss_fig_path}")
    
    # -------------------------------------------------------------
    # Plot 2: Reward Margin Comparison
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    
    # Standard DPO curves
    ax.plot(std_metrics['train_steps'], std_metrics['train_margin'], label='Standard DPO (Train)', color=STD_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax.plot(std_metrics['eval_steps'], std_metrics['eval_margin'], label='Standard DPO (Val)', color=STD_VAL_COLOR, linestyle='--', marker='o', markersize=5, linewidth=2)
    
    # OGPSA-DPO curves
    ax.plot(ogp_metrics['train_steps'], ogp_metrics['train_margin'], label='OGPSA-DPO (Train)', color=OGP_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax.plot(ogp_metrics['eval_steps'], ogp_metrics['eval_margin'], label='OGPSA-DPO (Val)', color=OGP_VAL_COLOR, linestyle='--', marker='s', markersize=5, linewidth=2)
    
    ax.set_xlabel("Steps", fontweight='semibold')
    ax.set_ylabel("Reward Margin ($r_{\\theta}(y_w|x) - r_{\\theta}(y_l|x)$)", fontweight='semibold')
    ax.grid(True)
    ax.legend(frameon=True, facecolor='white', framealpha=0.9)
    
    plt.tight_layout()
    margin_fig_path = os.path.join(OUTPUT_DIR, "training_margin_comparison.png")
    plt.savefig(margin_fig_path, dpi=300)
    plt.close()
    print(f"Saved margin plot to: {margin_fig_path}")
    
    # -------------------------------------------------------------
    # Plot 3: Dual Loss & Margin Side-by-Side (Ideal for Paper)
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.0))
    
    # Left: Loss
    ax1.plot(std_metrics['train_steps'], std_metrics['train_loss'], label='Standard DPO (Train)', color=STD_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax1.plot(std_metrics['eval_steps'], std_metrics['eval_loss'], label='Standard DPO (Val)', color=STD_VAL_COLOR, linestyle='--', marker='o', markersize=4, linewidth=2)
    ax1.plot(ogp_metrics['train_steps'], ogp_metrics['train_loss'], label='OGPSA-DPO (Train)', color=OGP_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax1.plot(ogp_metrics['eval_steps'], ogp_metrics['eval_loss'], label='OGPSA-DPO (Val)', color=OGP_VAL_COLOR, linestyle='--', marker='s', markersize=4, linewidth=2)
    ax1.set_xlabel("Training Steps", fontsize=11)
    ax1.set_ylabel("Loss (Log Scale)", fontsize=11)
    ax1.set_yscale('log')
    ax1.grid(True)
    ax1.legend(frameon=True)
    
    # Right: Margin
    ax2.plot(std_metrics['train_steps'], std_metrics['train_margin'], label='Standard DPO (Train)', color=STD_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax2.plot(std_metrics['eval_steps'], std_metrics['eval_margin'], label='Standard DPO (Val)', color=STD_VAL_COLOR, linestyle='--', marker='o', markersize=4, linewidth=2)
    ax2.plot(ogp_metrics['train_steps'], ogp_metrics['train_margin'], label='OGPSA-DPO (Train)', color=OGP_TRAIN_COLOR, linestyle='-', linewidth=2)
    ax2.plot(ogp_metrics['eval_steps'], ogp_metrics['eval_margin'], label='OGPSA-DPO (Val)', color=OGP_VAL_COLOR, linestyle='--', marker='s', markersize=4, linewidth=2)
    ax2.set_xlabel("Training Steps", fontsize=11)
    ax2.set_ylabel("Reward Margin ($r_{\\theta}(y_w|x) - r_{\\theta}(y_l|x)$)", fontsize=11)
    ax2.grid(True)
    ax2.legend(frameon=True)
    
    plt.tight_layout()
    side_fig_path = os.path.join(OUTPUT_DIR, "training_dynamics_comparison.png")
    plt.savefig(side_fig_path, dpi=300)
    plt.close()
    print(f"Saved side-by-side plot to: {side_fig_path}")

if __name__ == '__main__':
    main()
