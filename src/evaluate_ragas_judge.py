"""
LLM-as-a-Judge & RAGAS Evaluation Script for Summarization Utility
Uses OpenRouter API (or any OpenAI-compatible endpoint) to score capability summaries
on Faithfulness, Relevance, Conciseness, and Overall Quality.

Usage:
    python src/evaluate_ragas_judge.py --results_file results/capability_results.json --model "google/gemini-2.5-pro-preview-0325"
    python src/evaluate_ragas_judge.py --results_file results/capability_results.json --model "meta-llama/llama-3-70b-instruct" --use_ragas
"""

import os
import sys
import json
import re
import argparse
import time
import requests
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data_loader import DataLoader

def get_doc_map(limit=500):
    dl = DataLoader("datasets")
    try:
        docs = dl._load_vlsp(limit=limit)
    except Exception as e:
        print(f"[WARN] Could not load via _load_vlsp ({e}), trying load_all...")
        docs = dl.load_all(["vlsp"], limit_per_dataset=limit)
    return {doc.id: doc for doc in docs}

def call_openrouter_judge(doc_text, ref_summary, cand_summary, model, api_key, provider="google"):
    prompt = f"""Bạn là một chuyên gia đánh giá chất lượng tóm tắt văn bản tiếng Việt (LLM-as-a-Judge).
Nhiệm vụ của bạn là đánh giá bản Tóm tắt cần đánh giá dựa trên Văn bản gốc và Tóm tắt tham khảo (chuẩn).

--- VĂN BẢN GỐC ---
{doc_text[:2500]}

--- TÓM TẮT THAM KHẢO ---
{ref_summary}

--- TÓM TẮT CẦN ĐÁNH GIÁ ---
{cand_summary}

Hãy đánh giá Tóm tắt cần đánh giá trên thang điểm từ 1 đến 5 cho 3 tiêu chí sau:
1. Faithfulness (Tính trung thực 1-5): Bản tóm tắt có trung thực với văn bản gốc không? Có bị bịa đặt (hallucinate) thông tin sai lệch không? (5 = Hoàn toàn chính xác, không bịa đặt; 1 = Bịa đặt hoàn toàn hoặc sai sự thật).
2. Relevance / Coverage (Độ bao phủ & Liên quan 1-5): Bản tóm tắt có nắm bắt được các ý chính và thông điệp quan trọng nhất của bài viết không? (5 = Đầy đủ ý chính, không sót thông tin quan trọng; 1 = Lạc đề hoặc bỏ sót toàn bộ ý chính).
3. Conciseness & Structure (Tính súc tích & Cấu trúc 1-5): Bản tóm tắt có ngắn gọn, súc tích, trình bày rõ ràng (ví dụ gạch đầu dòng) và không bị lặp từ/dài dòng không? (5 = Cực kỳ súc tích, rõ ràng, không lặp lại; 1 = Dài dòng, lặp từ, rườm rà).

Vui lòng TRẢ LỜI DUY NHẤT bằng một định dạng JSON hợp lệ như sau (không kèm văn bản khác):
{{
  "faithfulness": <int 1-5>,
  "relevance": <int 1-5>,
  "conciseness": <int 1-5>,
  "reasoning": "<lời giải thích ngắn gọn bằng tiếng Việt>"
}}
"""

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            if provider == "google" or "gemini" in model.lower():
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                content = response.text.strip()
            else:
                from openai import OpenAI
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content.strip()
            
            if content.startswith("```"):
                content = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", content).strip()
            res_json = json.loads(content)
            return res_json
        except Exception as e:
            err_str = str(e)
            if "404" in err_str or "not found" in err_str.lower():
                print(f"\n[ERROR] Model '{model}' not found on {provider} (404). Please pass a valid model string.")
                sys.exit(1)
            if attempt < max_retries:
                sleep_sec = min(60, 5 * (2 ** (attempt - 1)))
                print(f"\n[WARN] Attempt {attempt}/{max_retries} failed ({err_str[:80]}...). Retrying in {sleep_sec}s...", end="", flush=True)
                time.sleep(sleep_sec)
            else:
                print(f"\n[ERROR] All {max_retries} retries failed for sample: {e}")
                return None

def run_ragas_eval(doc_map, results_data, model_str, api_key, provider="google"):
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy
        from datasets import Dataset
    except ImportError:
        print("[ERROR] RAGAS or datasets not installed. Please run: pip install ragas datasets")
        return
        
    if provider == "google" or "gemini" in model_str.lower():
        from langchain_google_genai import ChatGoogleGenerativeAI
        print(f"[RAGAS] Initializing Google GenAI ChatGoogleGenerativeAI with model {model_str}...")
        llm = ChatGoogleGenerativeAI(
            model=model_str,
            google_api_key=api_key,
            temperature=0.1
        )
    else:
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
        from langchain_openai import ChatOpenAI
        print(f"[RAGAS] Initializing OpenRouter ChatOpenAI with model {model_str}...")
        llm = ChatOpenAI(
            model=model_str,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.1
        )
    
    # Try to set local embeddings or fallback
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        print("[RAGAS] Using local HuggingFace embeddings for vector similarity.")
    except Exception:
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
            print("[RAGAS] Using local HuggingFace embeddings for vector similarity.")
        except Exception:
            if provider == "google" or "gemini" in model_str.lower():
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
                print("[RAGAS] Using GoogleGenerativeAIEmbeddings.")
            else:
                from langchain_openai import OpenAIEmbeddings
                embeddings = OpenAIEmbeddings(openai_api_key=api_key, openai_api_base="https://openrouter.ai/api/v1")
                print("[RAGAS] Using OpenRouter OpenAIEmbeddings.")
            
    # Override LLM and Embeddings in RAGAS metrics
    faithfulness.llm = llm
    answer_relevancy.llm = llm
    answer_relevancy.embeddings = embeddings
    
    for model_key, items in results_data.items():
        if not items:
            continue
        print(f"\n[RAGAS] Evaluating model: {model_key} ({len(items)} samples)...")
        data_dict = {
            "question": [], # Prompt/instruction
            "answer": [],   # Candidate summary
            "contexts": [], # Source document
            "ground_truth": [] # Ref summary
        }
        for it in items:
            doc = doc_map.get(it["doc_id"])
            if not doc:
                continue
            data_dict["question"].append("Hãy tóm tắt văn bản sau đây một cách súc tích và chính xác.")
            data_dict["answer"].append(it["output"])
            data_dict["contexts"].append([doc.document])
            data_dict["ground_truth"].append(doc.reference_summary)
            
        dataset = Dataset.from_dict(data_dict)
        score = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
        print(f"--> RAGAS Results for {model_key}: {score}")

def main():
    parser = argparse.ArgumentParser(description="LLM Judge / RAGAS Summarization Eval via Google AI Studio or OpenRouter")
    parser.add_argument("--results_file", type=str, default="results/capability_results.json", help="Path to capability JSON")
    parser.add_argument("--model", type=str, default="gemini-3.1-flash-lite", help="Model string (e.g. gemini-3.1-flash-lite or openrouter/auto)")
    parser.add_argument("--provider", type=str, default="google", choices=["google", "openrouter"], help="API provider (google or openrouter)")
    parser.add_argument("--api_key", type=str, default="", help="API key (or set GOOGLE_API_KEY / OPENROUTER_API_KEY env var)")
    parser.add_argument("--use_ragas", action="store_true", help="Use RAGAS framework instead of direct structured prompt")
    parser.add_argument("--limit", type=int, default=30, help="Max summaries to evaluate per model")
    args = parser.parse_args()
    
    api_key = args.api_key
    if not api_key:
        if args.provider == "google" or "gemini" in args.model.lower():
            api_key = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        else:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            
    if not api_key:
        print(f"[ERROR] No API key provided for provider '{args.provider}'! Set GOOGLE_API_KEY / OPENROUTER_API_KEY or pass --api_key.")
        sys.exit(1)
        
    if not os.path.exists(args.results_file):
        print(f"[ERROR] Results file not found: {args.results_file}")
        sys.exit(1)
        
    with open(args.results_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print("[INFO] Loading source document mapping from VLSP corpus...")
    doc_map = get_doc_map()
    print(f"[INFO] Loaded {len(doc_map)} source documents.")
    
    if args.use_ragas:
        run_ragas_eval(doc_map, data, args.model, api_key, provider=args.provider)
        return
        
    # Direct Structured LLM-as-a-Judge Evaluation
    print(f"\n[JUDGE] Starting structured evaluation using {args.provider.upper()} model: {args.model}")
    print("="*95)
    print(f"{'Model Name':<22} | {'Faithfulness':<14} | {'Relevance':<14} | {'Conciseness':<14} | {'Overall (1-5)':<14}")
    print("-" * 95)
    
    summary_scores = {}
    
    for model_key in ["Base_Model", "Baseline_Filter", "Standard_DPO", "OGPSA_DPO"]:
        items = data.get(model_key, [])
        if not items:
            continue
        
        items_to_eval = items[:args.limit]
        f_scores, r_scores, c_scores = [], [], []
        
        print(f"[Evaluating {model_key}...] (processing {len(items_to_eval)} samples)", end="", flush=True)
        for idx, it in enumerate(items_to_eval):
            doc = doc_map.get(it["doc_id"])
            if not doc:
                continue
            res = call_openrouter_judge(doc.document, doc.reference_summary, it["output"], args.model, api_key, provider=args.provider)
            if res is not None:
                f_scores.append(float(res.get("faithfulness", 3)))
                r_scores.append(float(res.get("relevance", 3)))
                c_scores.append(float(res.get("conciseness", 3)))
                print(".", end="", flush=True)
            time.sleep(4.0) # rate limit politeness for free tiers
        print(" Done!")
        
        if f_scores:
            avg_f = sum(f_scores) / len(f_scores)
            avg_r = sum(r_scores) / len(r_scores)
            avg_c = sum(c_scores) / len(c_scores)
            avg_o = (avg_f + avg_r + avg_c) / 3.0
            summary_scores[model_key] = {"faithfulness": avg_f, "relevance": avg_r, "conciseness": avg_c, "overall": avg_o}
            print(f"{model_key:<22} | {avg_f:>14.2f} | {avg_r:>14.2f} | {avg_c:>14.2f} | {avg_o:>14.2f}")
    
    print("="*95)
    
    # Save results to JSON
    out_file = "results/llm_judge_scores.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_scores, f, indent=2, ensure_ascii=False)
    print(f"\n[SUCCESS] Judge scores saved to {out_file}")

if __name__ == "__main__":
    main()
