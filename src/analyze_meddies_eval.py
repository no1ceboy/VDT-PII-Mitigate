"""Analyze Meddies evaluation results and extract interpretable examples.

This is intentionally dependency-free so it can run on the offline machine.
It accepts the JSON produced by survey_pii_leakage.py or the richer JSON
produced by evaluate_meddies_judge.py.  Judge scores are required for utility
quadrants; a survey-only file still produces privacy summaries and examples.

Examples:
    python src/analyze_meddies_eval.py \
      --results-file results/benchmarks/meddies_judge_scores.json \
      --output-file results/benchmarks/api_meddies_quadrants.md

    python src/analyze_meddies_eval.py \
      --results-file results/survey_leakage_stats_few_shot_patched.json \
      --output-file results/benchmarks/few_shot_examples.md \
      --examples-per-quadrant 5
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from statistics import mean, pstdev


LEAK_PATTERN = re.compile(r"Leaked\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def get_records(data):
    records = data.get("detailed_results", [])
    if records:
        return [dict(record) for record in records]

    # Some older judge outputs store scores under a model-specific summary.
    flattened = []
    for model, model_records in data.get("results", {}).items():
        for record in model_records or []:
            item = dict(record)
            item.setdefault("model", model)
            flattened.append(item)
    return flattened


def parse_leak_count(record):
    if not record.get("is_leaked"):
        return 0
    details = str(record.get("new_leak_details") or record.get("leak_details") or "")
    match = LEAK_PATTERN.search(details)
    return int(match.group(1)) if match else 1


def utility_scores(record):
    linguistic_values = [record.get("coherence"), record.get("fluency")]
    clinical_values = [record.get("faithfulness_ragas"), record.get("coverage_ragas")]

    def average(values):
        values = [float(value) for value in values if isinstance(value, (int, float))]
        return mean(values) if values else None

    return average(linguistic_values), average(clinical_values)


def truncate(value, limit):
    value = str(value or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...[truncated]..."


def classify(record, utility_threshold):
    linguistic, clinical = utility_scores(record)
    safe = not bool(record.get("is_leaked"))

    def label(utility):
        if utility is None:
            return None
        if safe and utility >= utility_threshold:
            return "Q1 - Ideal: safe and useful"
        if safe:
            return "Q2 - Safe but low utility"
        if utility >= utility_threshold:
            return "Q3 - Leaking but useful"
        return "Q4 - Leaking and low utility"

    return {
        "linguistic_utility": linguistic,
        "clinical_utility": clinical,
        "linguistic_quadrant": label(linguistic),
        "clinical_quadrant": label(clinical),
        "leaked_count": parse_leak_count(record),
    }


def enrich(records, utility_threshold):
    enriched = []
    for index, record in enumerate(records):
        item = dict(record)
        item["_index"] = index
        item.update(classify(record, utility_threshold))
        item["_model"] = str(record.get("model") or "Unknown model")
        item["_doc_id"] = str(record.get("doc_id") or f"row_{index}")
        enriched.append(item)
    return enriched


def filter_models(records, requested_models):
    if not requested_models:
        return records
    wanted = {value.casefold() for value in requested_models}
    return [record for record in records if record["_model"].casefold() in wanted]


def select_examples(records, quadrant_key, quadrant, count):
    candidates = [record for record in records if record.get(quadrant_key) == quadrant]
    utility_key = "linguistic_utility" if "linguistic" in quadrant_key else "clinical_utility"

    # Deterministic, useful examples: severe leaks first for unsafe quadrants;
    # for safe quadrants, prefer the most/least useful boundary cases.
    if quadrant.startswith("Q3"):
        candidates.sort(key=lambda item: (item["leaked_count"], item.get(utility_key) or 0), reverse=True)
    elif quadrant.startswith("Q4"):
        candidates.sort(key=lambda item: (item["leaked_count"], -(item.get(utility_key) or 0)), reverse=True)
    elif quadrant.startswith("Q1"):
        candidates.sort(key=lambda item: item.get(utility_key) or 0, reverse=True)
    else:
        candidates.sort(key=lambda item: item.get(utility_key) or 0)
    return candidates[:count]


def pct(value):
    return "n/a" if value is None else f"{value:.1%}"


def score(value):
    return "n/a" if value is None else f"{value:.2f}"


def summary_table(records, quadrant_key):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["_model"]].append(record)

    lines = [
        "| Model | Documents | Leaking documents | Leak rate | Q1 | Q2 | Q3 | Q4 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in sorted(grouped):
        items = grouped[model]
        leaks = sum(1 for item in items if item.get("is_leaked"))
        counts = Counter(item.get(quadrant_key) for item in items)
        def count(prefix):
            return sum(value for key, value in counts.items() if str(key).startswith(prefix))
        lines.append(
            f"| {model} | {len(items)} | {leaks} | {pct(leaks / len(items) if items else None)} | "
            f"{pct(count('Q1') / len(items) if items else None)} | "
            f"{pct(count('Q2') / len(items) if items else None)} | "
            f"{pct(count('Q3') / len(items) if items else None)} | "
            f"{pct(count('Q4') / len(items) if items else None)} |"
        )
    return lines


def score_summary(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["_model"]].append(record)
    lines = [
        "| Model | Linguistic utility mean | Linguistic SD | Clinical utility mean | Clinical SD |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in sorted(grouped):
        items = grouped[model]
        linguistic = [item["linguistic_utility"] for item in items if item["linguistic_utility"] is not None]
        clinical = [item["clinical_utility"] for item in items if item["clinical_utility"] is not None]
        lines.append(
            f"| {model} | {score(mean(linguistic) if linguistic else None)} | "
            f"{score(pstdev(linguistic) if len(linguistic) > 1 else None)} | "
            f"{score(mean(clinical) if clinical else None)} | "
            f"{score(pstdev(clinical) if len(clinical) > 1 else None)} |"
        )
    return lines


def example_markdown(record, max_chars):
    leaks = record.get("new_leak_details") or record.get("leak_details") or "No leak details"
    return "\n".join([
        f"#### `{record['_doc_id']}` — {record['_model']}",
        "",
        f"- Leak: **{bool(record.get('is_leaked'))}**; estimated leaked items: **{record['leaked_count']}**",
        f"- Linguistic utility: **{score(record['linguistic_utility'])}**; clinical utility: **{score(record['clinical_utility'])}**",
        f"- Leak details: `{leaks}`",
        "",
        "**Input / prompt**",
        "",
        "```text",
        truncate(record.get("prompt") or record.get("document") or "[not stored]", max_chars),
        "```",
        "",
        "**Generated output**",
        "",
        "```text",
        truncate(record.get("generated_summary") or record.get("output") or "[not stored]", max_chars),
        "```",
        "",
    ])


def build_report(records, input_file, threshold, examples_per_quadrant, max_chars):
    models = sorted({record["_model"] for record in records})
    has_utility = any(
        record["linguistic_utility"] is not None or record["clinical_utility"] is not None
        for record in records
    )
    lines = [
        "# Meddies evaluation analysis",
        "",
        f"Input: `{input_file}`  ",
        f"Records: **{len(records)}**  ",
        f"Models: **{len(models)}**  ",
        f"Utility threshold: **{threshold:.2f}/5.00**  ",
        f"Examples per quadrant: **{examples_per_quadrant}**",
        "",
        "## How to read this report",
        "",
        "A document is safe when `is_leaked` is false. Q1 is the desired outcome. Q2 is safe but has low utility. Q3 is dangerous because it leaks despite being useful. Q4 both leaks and performs poorly.",
        "",
    ]

    if not records:
        lines.append("No evaluation records were found.")
        return "\n".join(lines) + "\n"

    if not has_utility:
        lines.extend([
            "**Warning:** This file contains privacy results but no judge utility scores. Full quadrants cannot be computed. Run `evaluate_meddies_judge.py` on this result file first, then analyze the judge output.",
            "",
        ])

    lines.extend(["## Privacy summary", ""])
    grouped = defaultdict(list)
    for record in records:
        grouped[record["_model"]].append(record)
    lines.extend([
        "| Model | Documents | Leaking documents | Leak rate | Estimated leaked items | Average leaked items/doc |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for model in sorted(grouped):
        items = grouped[model]
        leaks = sum(item["leaked_count"] for item in items)
        leaking_docs = sum(1 for item in items if item.get("is_leaked"))
        lines.append(
            f"| {model} | {len(items)} | {leaking_docs} | {pct(leaking_docs / len(items))} | "
            f"{leaks} | {leaks / len(items):.2f} |"
        )

    if has_utility:
        lines.extend(["", "## Linguistic utility quadrants", "", "Uses `(coherence + fluency) / 2`.", ""])
        lines.extend(summary_table(records, "linguistic_quadrant"))
        lines.extend(["", "## Clinical utility quadrants", "", "Uses `(faithfulness_ragas + coverage_ragas) / 2`.", ""])
        lines.extend(summary_table(records, "clinical_quadrant"))
        lines.extend(["", "## Utility score distribution", ""])
        lines.extend(score_summary(records))

        for title, key in (("Linguistic", "linguistic_quadrant"), ("Clinical", "clinical_quadrant")):
            lines.extend(["", f"## {title} quadrant examples", ""])
            for model in sorted(grouped):
                lines.extend([f"### {model}", ""])
                found = False
                for quadrant in (
                    "Q1 - Ideal: safe and useful",
                    "Q2 - Safe but low utility",
                    "Q3 - Leaking but useful",
                    "Q4 - Leaking and low utility",
                ):
                    examples = select_examples(grouped[model], key, quadrant, examples_per_quadrant)
                    lines.extend([f"#### {quadrant}", ""])
                    if not examples:
                        lines.append("No examples in this quadrant.\n")
                    else:
                        found = True
                        lines.extend(example_markdown(item, max_chars) for item in examples)
                if not found:
                    lines.append("No examples were available for this model.\n")
    else:
        lines.extend(["", "## Privacy-only examples", ""])
        for model in sorted(grouped):
            lines.extend([f"### {model}", ""])
            leaking = sorted(grouped[model], key=lambda item: item["leaked_count"], reverse=True)[:examples_per_quadrant]
            clean = [item for item in grouped[model] if not item.get("is_leaked")][:examples_per_quadrant]
            lines.extend(["#### Largest leaks", ""])
            lines.extend(example_markdown(item, max_chars) for item in leaking) if leaking else lines.append("No leaking examples.\n")
            lines.extend(["#### Clean examples", ""])
            lines.extend(example_markdown(item, max_chars) for item in clean) if clean else lines.append("No clean examples.\n")

    lines.extend([
        "## Interpretation cautions",
        "",
        "- The quadrant threshold is a reporting choice, not a clinical safety limit.",
        "- `is_leaked` and `leak_details` come from the configured PII evaluator; estimated leaked-item counts are parsed from the detail string.",
        "- A clean output can still omit important medical information; privacy and utility must be read together.",
        "- Review examples with the same `doc_id` across models when comparing methods fairly.",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Summarize Meddies eval results and extract quadrant examples.")
    parser.add_argument("--results-file", required=True, help="JSON from survey_pii_leakage.py or evaluate_meddies_judge.py")
    parser.add_argument("--output-file", required=True, help="Markdown report path to create")
    parser.add_argument("--model", dest="models", action="append", help="Only analyze this exact model name; repeat for multiple models")
    parser.add_argument("--utility-threshold", type=float, default=3.5, help="High-utility threshold on the 1-5 judge scale")
    parser.add_argument("--examples-per-quadrant", type=int, default=3, help="Examples to extract for each model/quadrant")
    parser.add_argument("--max-chars", type=int, default=4000, help="Maximum prompt/output characters per example")
    args = parser.parse_args()

    if args.utility_threshold < 1 or args.utility_threshold > 5:
        parser.error("--utility-threshold must be between 1 and 5")
    if args.examples_per_quadrant < 1:
        parser.error("--examples-per-quadrant must be at least 1")
    if args.max_chars < 100:
        parser.error("--max-chars must be at least 100")
    if not os.path.exists(args.results_file):
        raise SystemExit(f"Results file does not exist: {args.results_file}")

    data = load_json(args.results_file)
    records = enrich(get_records(data), args.utility_threshold)
    records = filter_models(records, args.models)
    report = build_report(
        records,
        args.results_file,
        args.utility_threshold,
        args.examples_per_quadrant,
        args.max_chars,
    )

    output_dir = os.path.dirname(os.path.abspath(args.output_file))
    os.makedirs(output_dir, exist_ok=True)
    with open(args.output_file, "w", encoding="utf-8") as handle:
        handle.write(report)

    print(f"Analyzed {len(records)} records from {args.results_file}")
    print(f"Report written to {args.output_file}")


if __name__ == "__main__":
    main()
