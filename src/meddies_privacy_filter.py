"""
Baseline Defense: Meddies Privacy Filter
This script uses the Meddies/meddies-pii-v2 Token Classification model 
to redact sensitive PII tokens from documents *before* summarization.
"""

import argparse
from transformers import pipeline

class MeddiesPrivacyFilter:
    def __init__(self, model_path: str, device: str = "cpu"):
        print(f"Loading Meddies Privacy Filter from {model_path} on {device}...")
        # device mapping for pipeline: 0 for cuda, -1 for cpu
        device_id = 0 if "cuda" in device else -1
        
        try:
            # We use aggregation_strategy="simple" to automatically merge sub-word tokens
            # into whole entity words and provide clean start/end character offsets.
            self.extractor = pipeline(
                "token-classification", 
                model=model_path, 
                aggregation_strategy="simple",
                device=device_id
            )
            print("Meddies OPF Runtime loaded successfully!")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.extractor = None
        
    def redact(self, text: str) -> str:
        """
        Detects PII in the text and replaces it with a generic <REDACTED> tag.
        """
        if not self.extractor:
            print("Privacy filter not loaded. Returning original text.")
            return text
            
        # Predict PII spans
        results = self.extractor(text)
        
        # Sort spans by start index in reverse order to avoid offset shifting when replacing
        redacted_text = text
        sorted_entities = sorted(results, key=lambda x: x["start"], reverse=True)
        
        for ent in sorted_entities:
            start = ent["start"]
            end = ent["end"]
            label = ent.get("entity_group", "PII")
            
            # Clean up BIO tags if they leaked through aggregation
            if label.startswith("B-") or label.startswith("I-"):
                label = label[2:]
                
            # Replace the PII with a placeholder tag
            placeholder = f"<{label.upper()}>"
            redacted_text = redacted_text[:start] + placeholder + redacted_text[end:]
            
        return redacted_text

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meddies Token Classification Privacy Filter")
    parser.add_argument("--model-path", type=str, default="Meddies/meddies-pii-v2", help="Local path or HuggingFace ID")
    parser.add_argument("--device", type=str, default="cpu", help="Device to load model on (cpu or cuda)")
    args = parser.parse_args()
    
    # Quick demonstration
    sample_text = "Bệnh nhân Nguyễn Văn A, sinh năm 1980, số điện thoại 0912345678, địa chỉ tại 123 Đường B, Quận 1, TP.HCM."
    
    print("Initializing Meddies Privacy Filter Baseline...")
    defense = MeddiesPrivacyFilter(model_path=args.model_path, device=args.device)
    
    if defense.extractor:
        safe_text = defense.redact(sample_text)
        print("\n--- Original Document ---")
        print(sample_text)
        print("\n--- Scrubbed Document ---")
        print(safe_text)
