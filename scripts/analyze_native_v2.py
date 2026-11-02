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
from pathlib import Path, PurePosixPath
from typing import Any

ARMS = ("original-agent", "deterministic-heuristic", "ordinary-laya", "trained-always", "selective-shadow")
NAMES = ("Original agent", "Deterministic heuristic", "Ordinary Laya", "Trained always", "Selective shadow")
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
METRICS = ("cli_wall_ms", "pipeline_wall_ms", *TOKEN_KEYS)
CHECKS = ("focused", "full", "public_contract")
PLAN_SHA = "0634b5648f675aa6cd08e47397397298f7b83e10b7eb1ab00e5afb86440752d1"
FAILED18_SHA = "7a4ef5d4ce2659216244619ef1c99870e77212c9044bfb01a10fbee8cd4eb975"
AMENDMENT_SHA = "2851023e7a647d9d32d65966c10063f60573c8d1d80477f2b07c309fd7a7dcfd"
REVIEW_SHA = "6663ad88ac0920ccfe49ca02bef789e7418a1349476bd36094a90021f238b59b"
DRIVER_SHA = "795acd32764313fb7d4afde9114c9c9e45211bc5b6d36d75f581ad9d7c185d9f"
PHASE = "reviewed-continuation-01"
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
PUBLICATION_EXTRAS = frozenset(
    {"SHA256SUMS.json", "authorization.json", "observer-provenance.json", "review-infrastructure-18.json"}
)
SUPPLEMENT_FILES = frozenset({"preflight/cachetools-getitem.json", "preflight/funcy-first.json"})
AMENDED_LIMIT = (
    "Trials 19 and 20 are a reviewed continuation after the phase-A halt and a publication/time gap, "
    "not an uninterrupted preregistered study. Trial 18 remains an invalid timeout of unknown cause, "
    "without retry or imputed usage. All combined estimates are post-amendment and descriptive. "
    "Compare each arm with its matching original-agent cohorts, not unequal-cohort arm means."
)
LIMITS = [
    "Two actual repositories, one supplied repair mutation per repository and two correlated repetitions. Repeated arm comparisons share original-agent baselines; they are not independent task samples.",
    "Descriptive observations only. No significance test, causal superiority, population reliability, monetary saving, energy saving or subscription-allowance estimate is established.",
    "Input tokens already include cached input tokens. Cached tokens are shown as a subset and are never added to input tokens. Reported counters are not monetary cost.",
    "Agent-side mandatory validation was requested and may be described in the final answer. Exact internal check execution and ordering were not retained or enforced by the observer. The separate post-run focused/full/contract results are directly observed.",
    "CLI wall time includes the native process and observer collection. Pipeline wall time additionally includes the three independent checks. Readiness hashing and subsequent postcondition audit are separate, with all-in attempt time also retained. Host load and operating-system/service caches are uncontrolled.",
    "Protocol-failed and missing observations remain explicit. They provide no paired estimate. Raw measurements on a failed-protocol observation may be displayed but are excluded from arm summaries and paired deltas.",
    "The trained policy remains withheld. Always-delegate is a controlled read-only experimental comparator, not production deployment. Selective shadow retains the failed policy's fallback.",
]


def read_json(path: Path, sources: dict[str, str], *, limit: int | None = None) -> Any:
    if limit is None:
        data = path.read_bytes()
    else:
        if path.is_symlink() or not path.is_file():
            raise ValueError("metadata must be a regular file, not a link")
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ValueError("metadata exceeds its byte bound")
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


def relative_name(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or "\\" in value:
        raise ValueError("unsafe evidence manifest path")
    path = PurePosixPath(value)
    if (
        not path.parts
        or path.is_absolute()
        or any(part in {".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise ValueError("unsafe evidence manifest path")
    return value


def valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def evidence_inventory(
    root: Path, sources: dict[str, str], budget: list[int], allowed: set[str]
) -> dict[str, str]:
    """Hash bounded regular evidence only; never follow model/case path metadata."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("evidence root must be a real directory")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("evidence links are forbidden")
        if path.is_file():
            name = relative_name(path.relative_to(root).as_posix())
            if name not in allowed:
                raise ValueError("unexpected evidence file; contents were not read")
            if len(result) >= 4096 or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("evidence inventory escaped its bound")
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    budget[0] += len(chunk)
                    if budget[0] > MAX_EVIDENCE_BYTES:
                        raise ValueError("combined evidence exceeds32MiB")
                    hasher.update(chunk)
            result[name] = hasher.hexdigest()
            sources[str(path.resolve())] = result[name]
    return result


def verified_continuation(
    study: Path, continuation: Path, plan: dict[str, Any], sources: dict[str, str]
) -> dict[str, Any]:
    """Check the historical amendment and all registered phase-A bytes offline."""
    budget = [0]
    attempt_names = {
        "candidate.py",
        "final-answer.txt",
        "independent-grader.py",
        "invocation.json",
        "result.json",
        "review.json",
        "started.json",
    }
    continuation_names = {
        "amendment.json",
        "review.json",
        "continue_native.py",
        "README.md",
        "SOURCE_SHA256SUMS.json",
        "tests/test_continuation.py",
    }
    continuation_names.update(f"attempts/{index}/{name}" for index in (19, 20) for name in attempt_names)
    continuation_names.update("phase-a-supplement/" + name for name in SUPPLEMENT_FILES)
    inventory = evidence_inventory(continuation, sources, budget, continuation_names)
    for name, expected in (
        ("amendment.json", AMENDMENT_SHA),
        ("review.json", REVIEW_SHA),
        ("continue_native.py", DRIVER_SHA),
    ):
        if inventory.get(name) != expected:
            raise ValueError(f"reviewed continuation {name} hash differs")
    amendment = read_json(continuation / "amendment.json", sources)
    review = read_json(continuation / "review.json", sources)
    if (
        amendment.get("phase") != PHASE
        or amendment.get("original_plan_sha256") != PLAN_SHA
        or amendment.get("original_failed_result_sha256") != FAILED18_SHA
        or amendment.get("driver_sha256") != DRIVER_SHA
        or review.get("driver_sha256") != DRIVER_SHA
        or review.get("amendment_sha256") != AMENDMENT_SHA
        or review.get("scope_indices") != [19, 20]
        or review.get("independent_review_complete") is not True
        or review.get("unresolved_blockers") != []
        or review.get("ordinary_outer_review_required") is not True
    ):
        raise ValueError("reviewed continuation scope or identity differs")
    if hashlib.sha256((study / "plan.json").read_bytes()).hexdigest() != PLAN_SHA:
        raise ValueError("original plan differs from reviewed amendment")
    expected = amendment.get("original_phase_files")
    if not isinstance(expected, dict) or len(expected) != 135:
        raise ValueError("amendment must register exactly135phase-A files")
    for name, value in expected.items():
        relative_name(name)
        if not valid_sha(value):
            raise ValueError("invalid registered phase-A hash")
    actual = evidence_inventory(study, sources, budget, set(expected) | PUBLICATION_EXTRAS)
    extras = set(actual) - set(expected)
    missing = set(expected) - set(actual)
    if extras - PUBLICATION_EXTRAS or missing - SUPPLEMENT_FILES:
        raise ValueError("phase-A file inventory differs from registered evidence")
    supplement_prefix = "phase-a-supplement/"
    supplement = {
        name[len(supplement_prefix) :]: value
        for name, value in inventory.items()
        if name.startswith(supplement_prefix)
    }
    if set(supplement) != missing:
        raise ValueError(
            "supplement may supply only the two registered absent preflight files, never override present files"
        )
    for name, expected_sha in expected.items():
        if actual.get(name, supplement.get(name)) != expected_sha:
            raise ValueError(f"registered phase-A bytes changed:{name}")
    if actual.get("attempts/18/result.json") != FAILED18_SHA:
        raise ValueError("original failed trial18 bytes changed")
    failed = read_json(study / "attempts/18/result.json", sources)
    if (
        failed.get("protocol_failure") is not True
        or failed.get("timed_out") is not True
        or failed.get("telemetry", {}).get("token_usage") is not None
        or failed.get("telemetry", {}).get("completed_turns") != 0
    ):
        raise ValueError("original trial18 timeout/usage state differs")
    cases = amendment.get("cases")
    if not isinstance(cases, list) or len(cases) != 2:
        raise ValueError("continuation must describe only trials19/20")
    for case, item in zip(cases, plan["order"][-2:], strict=True):
        if any(case.get(key) != item[key] for key in ("index", "task", "repeat", "arm", "prompt_sha256")):
            raise ValueError("continuation case metadata differs from original plan")
    closure = amendment.get("observer_sources")
    if not isinstance(closure, dict) or len(closure) != 15:
        raise ValueError("historical observer source closure is missing")
    for name, value in closure.items():
        relative_name(name)
        if not valid_sha(value):
            raise ValueError("invalid historical observer source hash")
    source_manifest = read_json(continuation / "SOURCE_SHA256SUMS.json", sources)
    if not isinstance(source_manifest, dict) or set(source_manifest) != {
        "continue_native.py",
        "README.md",
        "tests/test_continuation.py",
    }:
        raise ValueError("continuation source manifest differs from its bounded publication scope")
    if any(inventory.get(name) != value or not valid_sha(value) for name, value in source_manifest.items()):
        raise ValueError("published continuation source hash differs")
    allowed_continuation = {
        "amendment.json",
        "review.json",
        "continue_native.py",
        "README.md",
        "SOURCE_SHA256SUMS.json",
        "tests/test_continuation.py",
    }
    allowed_attempts = {
        "candidate.py",
        "final-answer.txt",
        "independent-grader.py",
        "invocation.json",
        "result.json",
        "review.json",
        "started.json",
    }
    for index in (19, 20):
        allowed_continuation.update(f"attempts/{index}/{name}" for name in allowed_attempts)
        folder = continuation / "attempts" / str(index)
        if inventory.get(f"attempts/{index}/review.json") != REVIEW_SHA:
            raise ValueError("per-attempt review differs from reviewed scope")
        binding = {
            "index": index,
            "phase": PHASE,
            "amendment_sha256": AMENDMENT_SHA,
            "review_sha256": REVIEW_SHA,
            "original_plan_sha256": PLAN_SHA,
        }
        item = plan["order"][index - 1]
        for name in ("started.json", "invocation.json", "result.json"):
            value = read_json(folder / name, sources)
            if any(value.get(key) != expected_value for key, expected_value in binding.items()):
                raise ValueError("new attempt phase/amendment/review binding differs")
            if name == "invocation.json" and value.get("prompt_sha256") != item["prompt_sha256"]:
                raise ValueError("continuation prompt differs")
            if name in {"started.json", "result.json"} and value.get("native_process_started") is not True:
                raise ValueError("continuation native start unavailable")
        result = read_json(folder / "result.json", sources)
        if any(
            result.get(key) is not expected_value
            for key, expected_value in {
                "protocol_failure": False,
                "task_success": True,
                "inference_observed": True,
                "observed_receipt_valid": True,
                "retrieval_protocol_valid": True,
                "immutable_files_preserved": True,
            }.items()
        ):
            raise ValueError("reviewed continuation lacks a valid independently successful model observation")
        if inventory.get(f"attempts/{index}/candidate.py") != result.get("candidate_sha256"):
            raise ValueError("continuation candidate hash differs from result")
    if set(inventory) != allowed_continuation | {supplement_prefix + name for name in missing}:
        raise ValueError("continuation contains unexpected or missing evidence files")
    return {
        "phase": PHASE,
        "indices": [19, 20],
        "scope_indices": [19, 20],
        "publication_time_gap": True,
        "amendment_sha256": AMENDMENT_SHA,
        "review_sha256": REVIEW_SHA,
        "driver_sha256": DRIVER_SHA,
        "original_plan_sha256": PLAN_SHA,
        "original_failed_result_sha256": FAILED18_SHA,
        "verified_phase_a_files": 135,
        "supplemented_preflight_files": sorted(missing),
        "publication_only_extras": {name: actual[name] for name in sorted(extras)},
        "historical_observer_checkout": amendment["observer_checkout"],
        "historical_observer_source_hashes": closure,
        "source_closure_qualification": "This is the source closure recorded and independently reviewed at amendment time, not a requirement that today's installed code equal that historical snapshot. The driver is hashed as evidence and is never executed by this analyzer.",
        "qualification": AMENDED_LIMIT,
    }


def build(study: Path, provenance: Path, continuation: Path | None = None) -> dict[str, Any]:
    sources: dict[str, str] = {}
    if continuation is not None and (study.is_symlink() or not study.is_dir()):
        raise ValueError("phase-A evidence root must be a real directory")
    plan = read_json(study / "plan.json", sources, limit=2 * 1024 * 1024 if continuation else None)
    if len(plan["order"]) != 20 or tuple(plan["arms"]) != ARMS:
        raise ValueError("expected the frozen twenty-observation five-arm study")
    metadata = read_json(provenance, sources, limit=2 * 1024 * 1024 if continuation else None)
    if metadata["plan_sha256"] != sources[str((study / "plan.json").resolve())]:
        raise ValueError("execution provenance refers to another plan")
    amendment = (
        verified_continuation(study, continuation, plan, sources) if continuation is not None else None
    )
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
        from_continuation = continuation is not None and item["index"] in (19, 20)
        folder = (continuation if from_continuation else study) / "attempts" / f"{item['index']:02}"
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
        if amendment is not None:
            row.update(
                phase=PHASE if from_continuation else "original-study",
                result_source=("continuation" if from_continuation else "execution")
                + f"/attempts/{item['index']:02}/result.json",
                result_sha256=sources.get(str(result_file.resolve())),
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
        if amendment is not None:
            lookup = {row["index"]: row for row in rows}
            paired_summary[-1]["matching_original_metrics"] = {
                key: describe([lookup[pair["original_index"]]["metrics"][key] for pair in group])
                for key in METRICS
            }
            paired_summary[-1]["matching_candidate_metrics"] = {
                key: describe([lookup[pair["candidate_index"]]["metrics"][key] for pair in group])
                for key in METRICS
            }
    final = all(row["protocol_valid"] for row in rows)
    value = {
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
    if amendment is not None:
        value.update(
            status=f"AMENDED PARTIAL COMPARISON: {value['completed_observations']} RESULTS, {value['protocol_valid_observations']} VALID",
            all_twenty_complete_and_protocol_valid=False,
            all_twenty_results_present=all(row["result_present"] for row in rows),
            independently_verified_successes=sum(
                row["independently_verified_success"] is True for row in rows
            ),
            model_inference_observations=sum(
                row["protocol_valid"] and row.get("inference_observed") is True for row in rows
            ),
            valid_pair_count=sum(pair["valid"] for pair in pairs),
            continuation=amendment,
            study_design="reviewed continuation after stop; not an uninterrupted preregistered study",
            source_summary_scope="Historical phase-A eighteen-attempt summary only; not a lagging combined-study summary.",
            limits=[*LIMITS, AMENDED_LIMIT],
            snapshot_note="Trials1–18 come only from the immutable original phase. Trials19/20 come only from the separately reviewed continuation. The original eighteen-attempt summary remains historical phase-A evidence, not an accumulating or lagging combined summary. Trial18 remains invalid with unavailable usage. No fully protocol-valid or uninterrupted study is claimed.",
        )
    return value


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
    if data.get("continuation"):
        return amended_markdown(data)
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


def amended_markdown(data: dict[str, Any]) -> str:
    continuation = data["continuation"]
    lines = [
        "# ReflexFoundry amended native comparison",
        "",
        f"**{data['status']}**",
        "",
        f"{data['completed_observations']}/20 actual results; {data['protocol_valid_observations']} protocol-valid; "
        f"{data['independently_verified_successes']} independently successful repairs; "
        f"{data['model_inference_observations']} valid model-inference observations; {data['valid_pair_count']}/16 valid pairs.",
        "",
        AMENDED_LIMIT,
        "",
        "## Matched-cohort comparisons",
        "",
        "Each candidate is compared only with the original-agent observations for the same task and repeat. "
        "The ordinary-Laya arm has three usable pairs; the other arms have four. Do not compare unequal-cohort arm means as an effect estimate. "
        "Negative deltas are smaller observed values, not causal savings. Cached tokens are already included within input.",
        "",
        "| Arm | Matched pairs | Original CLI s | Candidate CLI s | CLI delta s | Original pipeline s | Candidate pipeline s | Pipeline delta s | Input delta | Cached subset delta | Output delta |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in data["paired_summaries"]:
        original, candidate, delta = (
            row[key]
            for key in ("matching_original_metrics", "matching_candidate_metrics", "candidate_minus_original")
        )
        lines.append(
            f"| {row['arm']} | {row['valid_pairs']}/4 | {fmt(original['cli_wall_ms']['mean'], seconds=True)} | {fmt(candidate['cli_wall_ms']['mean'], seconds=True)} | {fmt(delta['cli_wall_ms']['mean'], seconds=True, signed=True)} | {fmt(original['pipeline_wall_ms']['mean'], seconds=True)} | {fmt(candidate['pipeline_wall_ms']['mean'], seconds=True)} | {fmt(delta['pipeline_wall_ms']['mean'], seconds=True, signed=True)} | {fmt(delta['input_tokens']['mean'], signed=True)} | {fmt(delta['cached_input_tokens']['mean'], signed=True)} | {fmt(delta['output_tokens']['mean'], signed=True)} |"
        )
    lines += [
        "",
        "## Amendment identity and historical source scope",
        "",
        f"Original phase: observations1–18, verified against all {continuation['verified_phase_a_files']} registered file hashes. "
        "Only the two registered absent preflight files may be resolved from the fixed continuation supplement. "
        "The four named publication-only extras remain outside that historical manifest and are disclosed by hash in JSON.",
        "",
        f"Continuation phase: `{continuation['phase']}`, indices19/20. Amendment SHA-256 `{continuation['amendment_sha256']}`; "
        f"review SHA-256 `{continuation['review_sha256']}`; driver SHA-256 `{continuation['driver_sha256']}`.",
        "",
        f"Historical continuation observer checkout: `{continuation['historical_observer_checkout']}`. "
        + continuation["source_closure_qualification"],
        "",
        data["source_summary_scope"],
        "",
    ]
    base = markdown({key: value for key, value in data.items() if key != "continuation"})
    base = base[base.index("## Arm summaries") :]
    base = base.replace(
        "## Arm summaries", "## Descriptive arm summaries (unequal cohorts; not an effect estimate)", 1
    )
    base = base.replace(
        "Only protocol-valid observations contribute to the descriptive means below.",
        "These absolute means retain each arm's available cohort and must not be ranked as an improvement comparison. Only protocol-valid observations contribute.",
        1,
    )
    return "\n".join(lines) + "\n" + base


def svg(data: dict[str, Any]) -> str:
    if data.get("continuation"):
        return amended_svg(data)
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


def amended_svg(data: dict[str, Any]) -> str:
    """Matched-pair deltas, rather than bars comparing unequal arm cohorts."""
    bg, ink, muted, rule, rust = "#f3f1e9", "#202720", "#62695e", "#d5d7cb", "#ce4c22"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="1090" viewBox="0 0 1680 1090" role="img" aria-labelledby="title desc"><title id="title">Amended native comparison: matched cohorts</title><desc id="desc">{html.escape(AMENDED_LIMIT)} Cached tokens are a subset of input. No causal or monetary claim.</desc><rect width="1680" height="1090" fill="{bg}"/>'
    ]

    def text(x: int, y: int, value: str, size: int = 20, color: str = ink, weight: int = 400) -> None:
        parts.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" font-weight="{weight}">{html.escape(value)}</text>'
        )

    def line(y: int) -> None:
        parts.append(f'<path d="M58 {y}H1622" stroke="{rule}" stroke-width="1"/>')

    text(58, 62, "REFLEXFOUNDRY / AMENDED NATIVE COMPARISON", 23, rust, 700)
    text(58, 113, "Matched cohorts. Preserved failure. Withheld deployment.", 35, ink, 700)
    text(58, 157, data["status"], 22, rust, 700)
    text(
        58,
        193,
        f"{data['completed_observations']}/20 results / {data['protocol_valid_observations']} valid / {data['independently_verified_successes']} successful / {data['model_inference_observations']} valid inference observations",
        21,
        muted,
    )
    text(
        58,
        229,
        f"{data['valid_pair_count']}/16 usable comparisons; two repository groups, correlated repeats and shared baselines.",
        20,
        muted,
    )
    line(251)
    headers = (
        (58, "ARM / VERIFIED SUCCESS"),
        (470, "PAIRS"),
        (610, "CLI DELTA (s)"),
        (850, "PIPELINE DELTA (s)"),
        (1160, "INPUT DELTA"),
        (1440, "OUTPUT"),
    )
    for x, label in headers:
        text(x, 294, label, 16, muted, 700)
    text(610, 325, "Mean candidate minus matching original-agent cohorts", 17, muted)
    paired = {row["arm"]: row for row in data["paired_summaries"]}
    for index, (arm, name) in enumerate(zip(data["arm_summaries"], NAMES, strict=True)):
        y = 382 + index * 105
        text(58, y, name, 24, ink, 700)
        text(
            58,
            y + 31,
            f"{arm['successes_protocol_valid']}/{arm['protocol_valid']} valid repairs; {arm['protocol_failed']} protocol failures",
            17,
            muted,
        )
        if arm["arm"] == "original-agent":
            text(470, y, "Shared reference", 17, muted)
            text(710, y, "Matched separately for each candidate arm", 21, muted)
        else:
            row = paired[arm["arm"]]
            delta = row["candidate_minus_original"]
            text(470, y, f"{row['valid_pairs']}/4", 23, ink, 700)
            text(610, y, fmt(delta["cli_wall_ms"]["mean"], seconds=True, signed=True), 24, rust)
            text(850, y, fmt(delta["pipeline_wall_ms"]["mean"], seconds=True, signed=True), 24, rust)
            text(1160, y, f"{delta['input_tokens']['mean']:+,.1f}", 20, ink)
            text(1440, y, f"{delta['output_tokens']['mean']:+,.1f}", 20, ink)
            text(
                850,
                y + 31,
                f"Cached subset delta: {delta['cached_input_tokens']['mean']:+,.1f}",
                17,
                muted,
            )
        line(y + 61)
    text(
        58,
        949,
        "Reviewed continuation after a halt and publication/time gap; this is not an uninterrupted study.",
        22,
        rust,
        700,
    )
    text(
        58,
        984,
        "Trial18 remains an invalid timeout of unknown cause. Usage is unavailable, not zero. No retry or imputation.",
        19,
        muted,
    )
    text(
        58,
        1016,
        "Actual independent post-run checks; agent-side internal validation is agent-reported. No causal or currency claim.",
        19,
        muted,
    )
    text(
        58,
        1048,
        "Cached tokens are included in input; repeated pairs share baselines. Arm means are not an effect estimate.",
        19,
        muted,
    )
    text(58, 1077, "Amendment SHA-256 " + data["continuation"]["amendment_sha256"], 14, muted)
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--continuation", type=Path, help="reviewed continuation evidence; never executed")
    parser.add_argument(
        "--output", type=Path, required=True, help="fresh output directory; never overwrite a prior snapshot"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; preserve previous snapshots")
    data = build(
        args.study.resolve(),
        args.provenance.resolve(),
        args.continuation.resolve() if args.continuation else None,
    )
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
