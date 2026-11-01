#!/usr/bin/env python3
"""Describe a frozen native study snapshot without running agent or task code.

Python standard library only. Every output directory must be fresh. Missing and
protocol-failed observations remain present; only valid pairs receive deltas.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARMS = ("original-agent", "deterministic-heuristic", "ordinary-laya", "trained-always", "selective-shadow")
NAMES = ("Original agent", "Deterministic heuristic", "Ordinary Laya", "Trained always", "Selective shadow")
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
METRICS = ("cli_wall_ms", "pipeline_wall_ms", *TOKEN_KEYS)
CHECKS = ("focused", "full", "public_contract")
LIMITS = [
    "Two actual repositories, one supplied repair mutation per repository and two correlated repetitions. Repeated arm comparisons share original-agent baselines; they are not independent task samples.",
    "Descriptive observations only. No significance test, causal superiority, population reliability, monetary saving, energy saving or subscription-allowance estimate is established.",
    "Input tokens already include cached input tokens. Cached tokens are shown as a subset and are never added to input tokens. Reported counters are not monetary cost.",
    "Agent-side mandatory validation was requested and may be described in the final answer. Exact internal check execution and ordering were not retained or enforced by the observer. The separate post-run focused/full/contract results are directly observed.",
    "CLI wall time includes the native process and observer collection. Pipeline wall time additionally includes the three independent checks. Readiness hashing and subsequent postcondition audit are separate, with all-in attempt time also retained. Host load and operating-system/service caches are uncontrolled.",
    "Protocol-failed and missing observations remain explicit. They provide no paired estimate. Raw measurements on a failed-protocol observation may be displayed but are excluded from arm summaries and paired deltas.",
    "The trained policy remains withheld. Always-delegate is a controlled read-only experimental comparator, not production deployment. Selective shadow retains the failed policy's fallback.",
]


def read_json(path: Path, sources: dict[str, str]) -> Any:
    data = path.read_bytes()
    value = json.loads(data)
    sources[str(path.resolve())] = hashlib.sha256(data).hexdigest()
    return value


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def describe(values: list[float | int]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def build(study: Path, provenance: Path) -> dict[str, Any]:
    sources: dict[str, str] = {}
    plan = read_json(study / "plan.json", sources)
    if len(plan["order"]) != 20 or tuple(plan["arms"]) != ARMS:
        raise ValueError("expected the frozen twenty-observation five-arm study")
    metadata = read_json(provenance, sources)
    if metadata["plan_sha256"] != sources[str((study / "plan.json").resolve())]:
        raise ValueError("execution provenance refers to another plan")
    source_summary = read_json(study / "summary.json", sources) if (study / "summary.json").exists() else None
    expected = {item["index"] for item in plan["order"]}
    if expected != set(range(1, 21)):
        raise ValueError("plan indices are not unique and complete")
    unexpected = [
        str(p)
        for p in (study / "attempts").glob("*/result.json")
        if not p.parent.name.isdigit() or int(p.parent.name) not in expected
    ]
    if unexpected:
        raise ValueError(f"unexpected attempt results: {unexpected}")
    rows: list[dict[str, Any]] = []
    for item in plan["order"]:
        row = {key: item[key] for key in ("index", "task", "repeat", "arm")}
        folder = study / "attempts" / f"{item['index']:02}"
        started = read_json(folder / "started.json", sources) if (folder / "started.json").exists() else None
        row.update(
            status="started-no-result" if started else "missing",
            native_process_started=bool(started and started.get("native_process_started")),
            result_present=False,
            protocol_valid=False,
            independently_verified_success=None,
            metrics={key: None for key in METRICS},
            independent=None,
            candidate_sha256=None,
        )
        result_file = folder / "result.json"
        if result_file.exists():
            result = read_json(result_file, sources)
            if any(result.get(key) != row[key] for key in ("index", "task", "repeat", "arm")):
                raise ValueError(f"result identity differs from frozen plan at{item['index']}")
            if (
                type(result.get("protocol_failure")) is not bool
                or type(result.get("task_success")) is not bool
            ):
                raise ValueError("result lacks explicit protocol/task status")
            checks = result.get("independent")
            complete_checks = isinstance(checks, dict) and all(
                isinstance(checks.get(key), dict) and type(checks[key].get("passed")) is bool
                for key in CHECKS
            )
            verified_success = all(checks[key]["passed"] for key in CHECKS) if complete_checks else None
            if complete_checks and verified_success != result["task_success"]:
                raise ValueError("declared task success disagrees with independent checks")
            usage = result.get("telemetry", {}).get("token_usage")
            metrics = {key: result.get(key) for key in ("cli_wall_ms", "pipeline_wall_ms")}
            metrics.update({key: usage.get(key) if isinstance(usage, dict) else None for key in TOKEN_KEYS})
            for key, value in metrics.items():
                if value is not None and (
                    not numeric(value) or value < 0 or (key in TOKEN_KEYS and type(value) is not int)
                ):
                    raise ValueError(f"invalid metric{key} at{item['index']}")
            if (
                metrics["cached_input_tokens"] is not None
                and metrics["input_tokens"] is not None
                and metrics["cached_input_tokens"] > metrics["input_tokens"]
            ):
                raise ValueError("cached tokens exceed inclusive input tokens")
            valid = not result["protocol_failure"]
            if valid and (not complete_checks or any(value is None for value in metrics.values())):
                raise ValueError("protocol-valid observation has incomplete required evidence")
            row.update(
                status="protocol-valid" if valid else "protocol-failed",
                result_present=True,
                protocol_valid=valid,
                independently_verified_success=verified_success,
                metrics=metrics,
                independent=checks,
                candidate_sha256=result.get("candidate_sha256"),
                inference_observed=result.get("inference_observed"),
                observed_receipt_valid=result.get("observed_receipt_valid"),
                immutable_files_preserved=result.get("immutable_files_preserved"),
                readiness_ms=result.get("readiness_ms"),
                postcondition_audit_ms=result.get("postcondition_audit_ms"),
                attempt_all_in_ms=result.get("attempt_all_in_ms"),
            )
        rows.append(row)
    arms = []
    for arm in ARMS:
        group = [row for row in rows if row["arm"] == arm]
        valid = [row for row in group if row["protocol_valid"]]
        completed = [row for row in group if row["result_present"]]
        arms.append(
            {
                "arm": arm,
                "planned": len(group),
                "completed": len(completed),
                "protocol_valid": len(valid),
                "protocol_failed": sum(row["status"] == "protocol-failed" for row in group),
                "independently_verified_successes_all_completed": sum(
                    row["independently_verified_success"] is True for row in completed
                ),
                "successes_protocol_valid": sum(
                    row["independently_verified_success"] is True for row in valid
                ),
                "metrics_protocol_valid": {
                    key: describe([row["metrics"][key] for row in valid]) for key in METRICS
                },
            }
        )
    pairs = []
    tasks = list(dict.fromkeys(row["task"] for row in rows))
    for task in tasks:
        for repeat in (1, 2):
            group = {row["arm"]: row for row in rows if row["task"] == task and row["repeat"] == repeat}
            baseline = group[ARMS[0]]
            for arm in ARMS[1:]:
                candidate = group[arm]
                reasons = [
                    f"{name}:{row['status']}"
                    for name, row in (("original", baseline), ("candidate", candidate))
                    if not row["protocol_valid"]
                ]
                pair = {
                    "task": task,
                    "repeat": repeat,
                    "arm": arm,
                    "original_index": baseline["index"],
                    "candidate_index": candidate["index"],
                    "valid": not reasons,
                    "unavailable_reasons": reasons,
                    "success_delta": None,
                    "candidate_minus_original": None,
                }
                if not reasons:
                    pair.update(
                        success_delta=int(candidate["independently_verified_success"])
                        - int(baseline["independently_verified_success"]),
                        candidate_minus_original={
                            key: candidate["metrics"][key] - baseline["metrics"][key] for key in METRICS
                        },
                    )
                pairs.append(pair)
    paired_summary = []
    for arm in ARMS[1:]:
        group = [pair for pair in pairs if pair["arm"] == arm and pair["valid"]]
        paired_summary.append(
            {
                "arm": arm,
                "planned_pairs": 4,
                "valid_pairs": len(group),
                "repository_groups": len({pair["task"] for pair in group}),
                "success_delta_sum": sum(pair["success_delta"] for pair in group),
                "candidate_minus_original": {
                    key: describe([pair["candidate_minus_original"][key] for pair in group])
                    for key in METRICS
                },
            }
        )
    final = all(row["protocol_valid"] for row in rows)
    return {
        "format": 1,
        "status": "FINAL DESCRIPTIVE SNAPSHOT" if final else "PARTIAL: NOT A COMPLETE COMPARISON",
        "all_twenty_complete_and_protocol_valid": final,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "planned_observations": 20,
        "completed_observations": sum(row["result_present"] for row in rows),
        "protocol_valid_observations": sum(row["protocol_valid"] for row in rows),
        "planned_repository_groups": len(tasks),
        "observations": rows,
        "arm_summaries": arms,
        "pairs": pairs,
        "paired_summaries": paired_summary,
        "limits": LIMITS,
        "execution_provenance": metadata,
        "input_sha256": sources,
        "source_summary_completed_at_read": source_summary.get("completed_attempts")
        if source_summary
        else None,
        "snapshot_note": "Derived from one read of each input. Study may be accumulating; source summary can lag results. Final status is recomputed from all twenty actual result files, not summary flags.",
        "currency_cost": None,
        "deployment": "withheld",
    }


def fmt(value: Any, *, seconds: bool = False, signed: bool = False) -> str:
    if value is None:
        return "unavailable"
    value = value / 1000 if seconds else value
    return (
        f"{value:+,.2f}"
        if signed and seconds
        else f"{value:,.2f}"
        if seconds
        else f"{value:+,}"
        if signed
        else f"{value:,}"
    )


def markdown(data: dict[str, Any]) -> str:
    lines = [
        "# ReflexFoundry native comparison",
        "",
        f"**{data['status']}**",
        "",
        f"{data['completed_observations']}/20 results; {data['protocol_valid_observations']}/20 protocol-valid observations. Two repository groups. Deployment withheld.",
        "",
        "## Arm summaries",
        "",
        "Only protocol-valid observations contribute to the descriptive means below. Success denominators show valid observations, with planned counts separately visible.",
        "",
        "| Arm | Completed / planned | Valid | Independent successes / valid | CLI mean s | Pipeline mean s | Input mean | Cached subset mean | Output mean |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in data["arm_summaries"]:
        m = row["metrics_protocol_valid"]
        lines.append(
            f"| {row['arm']} | {row['completed']}/{row['planned']} | {row['protocol_valid']} | {row['successes_protocol_valid']}/{row['protocol_valid']} | {fmt(m['cli_wall_ms']['mean'], seconds=True)} | {fmt(m['pipeline_wall_ms']['mean'], seconds=True)} | {fmt(m['input_tokens']['mean'])} | {fmt(m['cached_input_tokens']['mean'])} | {fmt(m['output_tokens']['mean'])} |"
        )
    lines += [
        "",
        "## Every planned observation",
        "",
        "Missing results are missing, even if a start was reserved. A started record alone is not proof of a live process. On protocol failure, raw metrics remain visible here and are excluded from comparison estimates.",
        "",
        "| Index | Repository task | Repeat | Arm | Status | Independent success | CLI s | Pipeline s | Input | Cached subset | Output |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in data["observations"]:
        m = row["metrics"]
        success = (
            "unavailable"
            if row["independently_verified_success"] is None
            else str(row["independently_verified_success"])
        )
        lines.append(
            f"| {row['index']} | {row['task']} | {row['repeat']} | {row['arm']} | {row['status']} | {success} | {fmt(m['cli_wall_ms'], seconds=True)} | {fmt(m['pipeline_wall_ms'], seconds=True)} | {fmt(m['input_tokens'])} | {fmt(m['cached_input_tokens'])} | {fmt(m['output_tokens'])} |"
        )
    lines += [
        "",
        "## Every planned pair",
        "",
        "All deltas are candidate minus the original-agent observation for the same repository task and repeat. The same original observation is shared by four arm comparisons. A negative time or token delta is a smaller observed value, without causal interpretation.",
        "",
        "| Repository task | Repeat | Arm | Original / candidate indices | Pair status | Success delta | CLI delta s | Pipeline delta s | Input delta | Cached subset delta | Output delta |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pair in data["pairs"]:
        m = pair["candidate_minus_original"] or {key: None for key in METRICS}
        status = "valid" if pair["valid"] else "; ".join(pair["unavailable_reasons"])
        lines.append(
            f"| {pair['task']} | {pair['repeat']} | {pair['arm']} | {pair['original_index']} / {pair['candidate_index']} | {status} | {fmt(pair['success_delta'], signed=True)} | {fmt(m['cli_wall_ms'], seconds=True, signed=True)} | {fmt(m['pipeline_wall_ms'], seconds=True, signed=True)} | {fmt(m['input_tokens'], signed=True)} | {fmt(m['cached_input_tokens'], signed=True)} | {fmt(m['output_tokens'], signed=True)} |"
        )
    lines += ["", "## Interpretation and boundaries", ""] + [f"- {limit}" for limit in data["limits"]]
    pro = data["execution_provenance"]
    lines += [
        "",
        "## Source identity",
        "",
        f"Observer checkout: `{pro['observer_checkout']}`. Preparation checkout: `{pro['original_preparation_checkout']}`.",
        "",
        "The plan freezes four observer files and the full per-case runtime. Imported observer dependencies are recorded separately in native-v2-execution-provenance.json; that record is not retroactive preregistration. This JSON report includes the exact SHA-256 of every read input.",
        "",
        data["snapshot_note"],
        "",
    ]
    return "\n".join(lines)


def svg(data: dict[str, Any]) -> str:
    bg, ink, muted, line, rust, green = "#f3f1e9", "#202720", "#62695e", "#d5d7cb", "#ce4c22", "#527160"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="1090" viewBox="0 0 1680 1090" role="img" aria-labelledby="title desc"><title id="title">ReflexFoundry native study comparison</title><desc id="desc">{html.escape(data["status"])}. All means use protocol-valid observations only. Input tokens include the cached subset. Two repository groups; no causal or monetary claim.</desc><rect width="1680" height="1090" fill="{bg}"/>'
    ]

    def text(x: float, y: float, value: str, size: int = 19, color: str = ink, weight: int = 400) -> None:
        parts.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" font-weight="{weight}">{html.escape(value)}</text>'
        )

    def rect(x: float, y: float, width: float, height: float, color: str) -> None:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{max(0, width)}" height="{height}" rx="2" fill="{color}"/>'
        )

    text(58, 62, "REFLEXFOUNDRY / NATIVE STUDY", 23, rust, 700)
    text(58, 113, "Real repairs. Observed costs. Withheld deployment.", 37, ink, 700)
    text(58, 157, data["status"], 22, rust, 700)
    text(
        58,
        191,
        f"{data['completed_observations']}/20 results • {data['protocol_valid_observations']}/20 protocol-valid • 2 repository groups • 2 repeats",
        20,
        muted,
    )
    rect(58, 214, 1564, 2, line)
    text(58, 257, "ARM / INDEPENDENT SUCCESS", 16, muted, 700)
    text(510, 257, "NATIVE CLI + COMPLETE PIPELINE", 16, muted, 700)
    text(1090, 257, "REPORTED TOKENS", 16, muted, 700)
    text(510, 284, "Means in seconds; dots show every valid observation", 16, muted)
    text(1090, 284, "Mean input includes cached subset; output separate", 16, muted)
    max_time = (
        max(
            (row["metrics"]["pipeline_wall_ms"] for row in data["observations"] if row["protocol_valid"]),
            default=1,
        )
        / 1000
        * 1.12
    )
    max_input = (
        max(
            (row["metrics"]["input_tokens"] for row in data["observations"] if row["protocol_valid"]),
            default=1,
        )
        * 1.12
    )
    for i, (row, name) in enumerate(zip(data["arm_summaries"], NAMES)):
        y = 330 + i * 117
        text(58, y, name, 23, ink, 700)
        text(
            58,
            y + 30,
            f"{row['successes_protocol_valid']}/{row['protocol_valid']} valid repairs passed",
            19,
            green,
        )
        text(
            58,
            y + 56,
            f"{row['completed']}/{row['planned']} complete; {row['protocol_failed']} protocol failures",
            16,
            muted,
        )
        metrics = row["metrics_protocol_valid"]
        if not row["protocol_valid"]:
            text(510, y + 20, "No valid observations yet", 18, muted)
            text(1090, y + 20, "No valid observations yet", 18, muted)
        else:
            for key, dy, color in (("cli_wall_ms", 2, green), ("pipeline_wall_ms", 32, rust)):
                value = metrics[key]["mean"] / 1000
                rect(510, y + dy, 385 * value / max_time, 13, color)
                for obs in data["observations"]:
                    if obs["arm"] == row["arm"] and obs["protocol_valid"]:
                        x = 510 + 385 * (obs["metrics"][key] / 1000) / max_time
                        parts.append(
                            f'<circle cx="{x}" cy="{y + dy + 6.5}" r="4" fill="{ink}" stroke="{bg}" stroke-width="1"/>'
                        )
                text(910, y + dy + 13, f"{value:.2f}s", 18, color)
            value = metrics["input_tokens"]["mean"]
            cached = metrics["cached_input_tokens"]["mean"]
            rect(1090, y + 2, 340 * value / max_input, 19, rust)
            rect(1090, y + 2, 340 * cached / max_input, 19, green)
            text(1090, y + 49, f"Input {value:,.0f} / cached subset {cached:,.0f}", 17, muted)
            text(1090, y + 74, f"Output {metrics['output_tokens']['mean']:,.0f}", 17, muted)
        rect(58, y + 90, 1564, 1, line)
    rect(510, 918, 19, 13, green)
    text(539, 930, "Native CLI", 17, muted)
    rect(691, 918, 19, 13, rust)
    text(720, 930, "Complete pipeline", 17, muted)
    text(
        58,
        976,
        "Descriptive only. Shared baselines and correlated repeats. No significance or causal superiority claim.",
        20,
        ink,
        700,
    )
    text(
        58,
        1009,
        "Independent post-run checks are verified. Agent-side check execution/order is agent-reported. Host/cache load uncontrolled.",
        18,
        muted,
    )
    text(
        58,
        1041,
        "No monetary, energy or subscription-allowance estimate. Missing/protocol-failed observations yield no paired estimate.",
        18,
        muted,
    )
    text(58, 1073, f"Plan SHA-256 {data['execution_provenance']['plan_sha256']}", 14, muted)
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="fresh output directory; never overwrite a prior snapshot"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; preserve previous snapshots")
    data = build(args.study.resolve(), args.provenance.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "analysis.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    (args.output / "analysis.md").write_text(markdown(data))
    (args.output / "comparison.svg").write_text(svg(data))
    outputs = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(args.output.iterdir())
    }
    (args.output / "SHA256SUMS.json").write_text(
        json.dumps(
            {
                "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "outputs": outputs,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "status": data["status"],
                "completed": data["completed_observations"],
                "protocol_valid": data["protocol_valid_observations"],
                "output": str(args.output.resolve()),
            }
        )
    )


if __name__ == "__main__":
    main()
