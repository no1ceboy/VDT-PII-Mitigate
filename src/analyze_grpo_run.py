"""Interpret GRPO logs without third-party dependencies.

Run this on the training machine, next to the GRPO output directory.  It reads
the JSONL files produced by train_grpo.py and writes a short Markdown report
back into that directory, so the raw logs do not need to leave an air-gapped
machine.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, OrderedDict, defaultdict
from statistics import mean


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                yield {"_invalid": True, "_line": line_number, "_error": str(exc)}


def fmt_number(value):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def fmt_pct(value):
    return "n/a" if value is None else f"{value:.1%}"


def safe_rate(numerator, denominator):
    return numerator / denominator if denominator else None


def stage_label(stage):
    reason = stage["reason"]
    return f"{reason} (step {stage['step']})"


def read_trace(path):
    stages = OrderedDict()
    invalid = 0
    for record in iter_jsonl(path):
        if record.get("_invalid"):
            invalid += 1
            continue
        if record.get("event") != "generation_trace":
            continue
        key = (record.get("step", 0), record.get("reason", "unknown"))
        if key not in stages:
            stages[key] = {
                "step": record.get("step", 0),
                "epoch": record.get("epoch"),
                "reason": record.get("reason", "unknown"),
                "records": [],
            }
        stages[key]["records"].append(record)

    result = []
    for stage in sorted(stages.values(), key=lambda item: (item["step"], item["reason"])):
        records = stage["records"]
        leaks = [item for item in records if item.get("leak")]
        refusals = [item for item in records if item.get("refusal")]
        lengths = [item.get("output_chars", 0) for item in records]
        stage.update({
            "documents": len(records),
            "leaks": len(leaks),
            "refusals": len(refusals),
            "leak_rate": safe_rate(len(leaks), len(records)),
            "refusal_rate": safe_rate(len(refusals), len(records)),
            "average_output_chars": mean(lengths) if lengths else None,
            "leaking_examples": leaks[:3],
            "refusal_examples": refusals[:3],
            "clean_examples": [
                item for item in records if not item.get("leak") and not item.get("refusal")
            ][:3],
        })
        result.append(stage)
    return result, invalid


def read_reward_debug(path):
    stats = defaultdict(lambda: {
        "count": 0,
        "rewards": [],
        "negative": 0,
        "positive": 0,
        "zero": 0,
        "leak_records": 0,
        "clean_records": 0,
        "leaked_items": Counter(),
        "completion_ids": set(),
        "completion_chars": [],
    })
    invalid = 0

    for record in iter_jsonl(path):
        if record.get("_invalid"):
            invalid += 1
            continue
        if record.get("event") != "reward_debug":
            continue
        component = record.get("component", "unknown")
        item = stats[component]
        reward = record.get("reward")
        item["count"] += 1
        if isinstance(reward, (int, float)) and not isinstance(reward, bool):
            reward = float(reward)
            item["rewards"].append(reward)
            if reward < 0:
                item["negative"] += 1
            elif reward > 0:
                item["positive"] += 1
            else:
                item["zero"] += 1
        item["completion_ids"].add(record.get("completion_id"))
        if isinstance(record.get("completion_chars"), (int, float)):
            item["completion_chars"].append(record["completion_chars"])
        leaked = record.get("leaked_items") or []
        if leaked:
            item["leak_records"] += 1
            item["leaked_items"].update(str(value) for value in leaked)
        else:
            item["clean_records"] += 1

    for item in stats.values():
        item["unique_completions"] = len(item["completion_ids"] - {None})
        item["average_reward"] = mean(item["rewards"]) if item["rewards"] else None
        item["minimum_reward"] = min(item["rewards"]) if item["rewards"] else None
        item["maximum_reward"] = max(item["rewards"]) if item["rewards"] else None
        item["average_completion_chars"] = (
            mean(item["completion_chars"]) if item["completion_chars"] else None
        )
        del item["completion_ids"]
        del item["rewards"]
        del item["completion_chars"]
    return dict(stats), invalid


def read_training_log(path):
    records = []
    invalid = 0
    for record in iter_jsonl(path):
        if record.get("_invalid"):
            invalid += 1
            continue
        if record.get("event") == "trainer_log":
            records.append(record)
    records.sort(key=lambda item: item.get("step", 0))
    return records, invalid


def get_config(output_dir):
    path = os.path.join(output_dir, "run_config.json")
    if not os.path.exists(path):
        return {}, None
    try:
        return load_json(path), path
    except (OSError, json.JSONDecodeError):
        return {}, path


def make_interpretation(config, stages, reward_stats, file_status):
    conclusions = []
    warnings = []

    if not stages:
        warnings.append(
            "No generation trace was found. This run cannot show whether behavior changed "
            "during training; --trace_generations must be enabled before the run."
        )
    else:
        first = stages[0]
        last = stages[-1]
        if first.get("leak_rate") is not None and last.get("leak_rate") is not None:
            delta = last["leak_rate"] - first["leak_rate"]
            if delta < -0.05:
                conclusions.append(
                    f"Leak rate improved from {fmt_pct(first['leak_rate'])} to "
                    f"{fmt_pct(last['leak_rate'])}."
                )
            elif delta > 0.05:
                conclusions.append(
                    f"Leak rate worsened from {fmt_pct(first['leak_rate'])} to "
                    f"{fmt_pct(last['leak_rate'])}; the run did not learn the intended privacy behavior."
                )
            else:
                conclusions.append(
                    f"Leak rate was essentially unchanged ({fmt_pct(first['leak_rate'])} to "
                    f"{fmt_pct(last['leak_rate'])})."
                )
        if first.get("refusal_rate") is not None and last.get("refusal_rate") is not None:
            if last["refusal_rate"] > first["refusal_rate"] + 0.05:
                conclusions.append("Refusals increased during training; the refusal penalty was insufficient.")
            elif last["refusal_rate"] < first["refusal_rate"] - 0.05:
                conclusions.append("Refusals decreased during training.")
        if first.get("average_output_chars") and last.get("average_output_chars"):
            ratio = last["average_output_chars"] / first["average_output_chars"]
            if ratio < 0.75:
                conclusions.append(
                    f"Average output length fell sharply ({first['average_output_chars']:.1f} to "
                    f"{last['average_output_chars']:.1f} chars); inspect whether the model learned to omit "
                    "too much or found short safe outputs."
                )
            elif ratio > 1.25:
                conclusions.append("Average output length increased substantially.")

    privacy = reward_stats.get("privacy")
    if not privacy:
        warnings.append(
            "No privacy reward records were found. Either reward debugging was disabled or the run did not "
            "call the expected privacy reward function."
        )
    else:
        if privacy["leak_records"] and privacy["clean_records"]:
            leak_rate = safe_rate(privacy["leak_records"], privacy["count"])
            conclusions.append(
                f"During sampled reward calls, the privacy evaluator marked {fmt_pct(leak_rate)} "
                "of completions as leaking."
            )
        if privacy["count"] and privacy["unique_completions"] < privacy["count"] * 0.4:
            warnings.append(
                "Reward debug contains many repeated completion IDs. Treat its line count as reward calls, "
                "not as the number of independent generations."
            )

    if config.get("debug_reward_limit") == 0:
        conclusions.append("Reward debugging was configured as unlimited; the file may be very large.")
    if config.get("trace_every_steps", 0) == 0 and stages:
        conclusions.append(
            "Tracing was configured at initial state, checkpoints, and final state; it was not recording every optimizer step."
        )

    missing = [name for name, exists in file_status.items() if not exists]
    if missing:
        warnings.append("Missing files: " + ", ".join(missing) + ".")

    return conclusions, warnings


def example_block(example):
    leaked = ", ".join(str(item) for item in (example.get("leaked_items") or [])) or "none"
    return (
        f"- `{example.get('example_id', 'unknown')}`; leak=`{example.get('leak')}`, "
        f"refusal=`{example.get('refusal')}`, leaked items=`{leaked}`\n\n"
        "```text\n"
        f"{example.get('generation', '')}\n"
        "```"
    )


def build_report(output_dir, config, stages, reward_stats, train_records, file_status, conclusions, warnings):
    lines = [
        "# GRPO run interpretation",
        "",
        "This report was generated locally from the GRPO JSON/JSONL files. It is an interpretation of the logged run, not a new evaluation.",
        "",
        "## Bottom line",
        "",
    ]
    lines.extend(f"- {item}" for item in (conclusions or ["There is not enough logged data to draw a conclusion."]))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)

    lines.extend(["", "## Run configuration", "", "```json", json.dumps(config, indent=2, ensure_ascii=False), "```"])

    lines.extend(["", "## Behavior across training", ""])
    if stages:
        lines.extend([
            "| Stage | Epoch | Documents | Leak rate | Refusal rate | Average chars |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for stage in stages:
            lines.append(
                f"| {stage_label(stage)} | {fmt_number(stage.get('epoch'))} | "
                f"{stage['documents']} | {fmt_pct(stage['leak_rate'])} | "
                f"{fmt_pct(stage['refusal_rate'])} | {fmt_number(stage['average_output_chars'])} |"
            )
    else:
        lines.append("No `generation_trace.jsonl` records were available.")

    lines.extend(["", "## Reward components", ""])
    if reward_stats:
        lines.extend([
            "| Component | Records | Unique completions | Average reward | Min | Max | Negative | Records with leaked items |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for component in sorted(reward_stats):
            item = reward_stats[component]
            lines.append(
                f"| {component} | {item['count']} | {item['unique_completions']} | "
                f"{fmt_number(item['average_reward'])} | {fmt_number(item['minimum_reward'])} | "
                f"{fmt_number(item['maximum_reward'])} | {item['negative']} | {item['leak_records']} |"
            )
        privacy = reward_stats.get("privacy")
        if privacy and privacy["leaked_items"]:
            lines.extend(["", "Most frequently logged leaked items in the privacy reward:", ""])
            lines.extend(f"- `{item}`: {count}" for item, count in privacy["leaked_items"].most_common(20))
    else:
        lines.append("No `reward_debug.jsonl` records were available.")

    if train_records:
        lines.extend(["", "## Trainer metrics", "", f"Logged metric records: {len(train_records)}", ""])
        keys = sorted({key for record in train_records for key in (record.get("metrics") or {})})
        lines.append("Metric keys: " + ", ".join(f"`{key}`" for key in keys))
        lines.append("")
        lines.append("Last logged metrics:")
        lines.extend(["", "```json", json.dumps(train_records[-1].get("metrics", {}), indent=2, ensure_ascii=False), "```"])

    if stages:
        latest = stages[-1]
        lines.extend(["", f"## Examples from latest stage: {stage_label(latest)}", ""])
        for title, key in (
            ("Leaking examples", "leaking_examples"),
            ("Refusal examples", "refusal_examples"),
            ("Clean examples", "clean_examples"),
        ):
            examples = latest.get(key) or []
            if not examples:
                continue
            lines.extend([f"### {title}", ""])
            lines.extend(example_block(example) for example in examples)
            lines.append("")

    lines.extend([
        "## How to interpret this",
        "",
        "- Use the behavior table for the real outcome: lower leak and refusal rates are better.",
        "- Use reward components to see what the optimizer was incentivized to do; reward values alone do not prove that the model improved.",
        "- A large length decrease together with unchanged leak rate means the model may be shortening or omitting content without learning reliable PII protection.",
        "- Compare the same `example_id` across stages in `generation_trace.jsonl` when diagnosing an individual failure.",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Interpret a local GRPO output directory.")
    parser.add_argument("output_dir", help="GRPO output directory, for example results/grpo_debug")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    if not os.path.isdir(output_dir):
        raise SystemExit(f"Output directory does not exist: {output_dir}")

    config, _ = get_config(output_dir)
    paths = {
        "generation_trace.jsonl": os.path.join(output_dir, "generation_trace.jsonl"),
        "reward_debug.jsonl": os.path.join(output_dir, "reward_debug.jsonl"),
        "training_log.jsonl": os.path.join(output_dir, "training_log.jsonl"),
    }
    file_status = {name: os.path.exists(path) for name, path in paths.items()}

    stages, trace_invalid = read_trace(paths["generation_trace.jsonl"]) if file_status["generation_trace.jsonl"] else ([], 0)
    reward_stats, reward_invalid = read_reward_debug(paths["reward_debug.jsonl"]) if file_status["reward_debug.jsonl"] else ({}, 0)
    train_records, train_invalid = read_training_log(paths["training_log.jsonl"]) if file_status["training_log.jsonl"] else ([], 0)

    conclusions, warnings = make_interpretation(config, stages, reward_stats, file_status)
    if trace_invalid or reward_invalid or train_invalid:
        warnings.append(
            f"Malformed JSONL lines skipped: trace={trace_invalid}, reward={reward_invalid}, trainer={train_invalid}."
        )

    report = build_report(output_dir, config, stages, reward_stats, train_records, file_status, conclusions, warnings)
    report_path = os.path.join(output_dir, "grpo_interpretation.md")
    summary_path = os.path.join(output_dir, "grpo_interpretation.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump({
            "output_dir": output_dir,
            "config": config,
            "stages": stages,
            "reward_components": {
                component: {
                    **item,
                    "leaked_items": dict(item["leaked_items"]),
                }
                for component, item in reward_stats.items()
            },
            "trainer_log_records": len(train_records),
            "conclusions": conclusions,
            "warnings": warnings,
        }, handle, indent=2, ensure_ascii=False)

    print("\nGRPO interpretation")
    print("===================")
    for item in conclusions:
        print(f"- {item}")
    for item in warnings:
        print(f"WARNING: {item}")
    print(f"\nReadable report: {report_path}")
    print(f"Machine-readable summary: {summary_path}")


if __name__ == "__main__":
    main()
