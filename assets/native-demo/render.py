#!/usr/bin/env python3
"""Render a silent evidence replay from a stopped, incomplete native comparison.

No native agent, inference or task code is executed. Uses local Pillow, FFmpeg
and system fonts. Editorial time is compressed and never represents process
speed. Existing renders and historical project media are never overwritten.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import selectors
import shutil
import signal
import statistics
import subprocess
import time
from functools import cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS, SECONDS = 1280, 720, 24, 44
PLAN_SHA = "0634b5648f675aa6cd08e47397397298f7b83e10b7eb1ab00e5afb86440752d1"
PAPER, INK, MUTED, RULE, RUST, GREEN = (
    "#f3f1e9",
    "#202720",
    "#62695e",
    "#d5d7cb",
    "#ce4c22",
    "#527160",
)
ARMS = (
    "original-agent",
    "deterministic-heuristic",
    "ordinary-laya",
    "trained-always",
    "selective-shadow",
)
NAMES = (
    "Original agent",
    "Deterministic heuristic",
    "Ordinary Laya",
    "Trained always",
    "Selective shadow",
)
CUES = (
    (0.0, "The supplied defect"),
    (6.0, "A proposal is not permission"),
    (13.0, "The trained-assisted repair"),
    (19.0, "Independent validation of trial04"),
    (25.0, "All five arms, incomplete comparison"),
    (34.0, "Timeout, protocol halt and withheld deployment"),
)
DIAGNOSTIC_TIMES = (
    0.0,
    2.5,
    5.95,
    6.0,
    6.6,
    10.5,
    12.95,
    13.0,
    16.0,
    18.95,
    19.0,
    22.0,
    24.95,
    25.0,
    29.0,
    33.95,
    34.0,
    36.0,
    37.95,
    40.0,
    43.95,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path, hashes: dict[str, str]) -> bytes:
    data = path.read_bytes()
    hashes[str(path.resolve())] = hashlib.sha256(data).hexdigest()
    return data


def js(path: Path, hashes: dict[str, str]) -> Any:
    return json.loads(read(path, hashes))


def digest(value: Any) -> str:
    # The frozen runtime's canonical public digest contract.
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def recorded_input_hash(analysis: dict[str, Any], relative: str) -> str:
    """Resolve a unique recorded suffix without opening historical absolute paths."""
    suffix = Path(relative).parts
    matches = [
        value
        for name, value in analysis.get("input_sha256", {}).items()
        if Path(name).parts[-len(suffix) :] == suffix
    ]
    if len(matches) != 1:
        raise ValueError(f"analysis input identity is absent or ambiguous:{relative}")
    return matches[0]


def load_evidence(
    study: Path, analysis_path: Path, task_source: Path, provenance_path: Path
) -> dict[str, Any]:
    hashes: dict[str, str] = {}
    plan = js(study / "plan.json", hashes)
    if sha(study / "plan.json") != PLAN_SHA:
        raise ValueError("frozen study plan hash changed")
    analysis = js(analysis_path, hashes)
    if (
        analysis.get("all_twenty_complete_and_protocol_valid") is not False
        or analysis.get("completed_observations") != 18
        or analysis.get("protocol_valid_observations") != 17
        or analysis.get("planned_repository_groups") != 2
    ):
        raise ValueError(
            "this replay requires the actual stopped18/20 analysis, not a complete claim"
        )
    stopped = js(study / "stopped.json", hashes)
    expected_stop = {
        "status": "stopped-incomplete",
        "failed_index": 18,
        "native_processes_started": 18,
        "protocol_valid_attempts": 17,
        "independently_successful_repairs": 17,
        "unattempted_indices": [19, 20],
        "usage_for_failed_attempt": None,
        "paired_comparisons_valid": 13,
        "new_native_launches_permitted_by_this_study": False,
    }
    if any(stopped.get(key) != value for key, value in expected_stop.items()):
        raise ValueError("stopped-study record does not match the factual storyboard")
    provenance = js(provenance_path, hashes)
    if (
        provenance.get("plan_sha256") != PLAN_SHA
        or analysis.get("execution_provenance") != provenance
    ):
        raise ValueError("analysis and observer provenance differ")
    if recorded_input_hash(analysis, "plan.json") != PLAN_SHA:
        raise ValueError("analysis was not derived from this frozen plan")
    raw_tasks = read(task_source, hashes)
    if (
        hashlib.sha256(raw_tasks).hexdigest()
        != plan["source_hashes"]["scripts/native_study_tasks.py"]
    ):
        raise ValueError("task-source bytes differ from frozen mutation source")
    mutation = None
    for node in ast.walk(ast.parse(raw_tasks.decode())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Task"
        ):
            values = {
                kw.arg: kw.value.value
                for kw in node.keywords
                if isinstance(kw.value, ast.Constant)
            }
            if values.get("name") == "funcy-first":
                mutation = values
    if (
        mutation is None
        or mutation["mutation_after"] != plan["tasks"][0]["mutation_after"]
    ):
        raise ValueError("could not bind Funcy mutation to actual frozen task source")
    observations = analysis.get("observations", [])
    byindex = {row["index"]: row for row in observations}
    if (
        len(observations) != 20
        or set(byindex) != set(range(1, 21))
        or tuple(plan["arms"]) != ARMS
    ):
        raise ValueError(
            "analysis does not preserve the twenty unique planned observations"
        )
    results: dict[int, dict[str, Any]] = {}
    for item in plan["order"]:
        index = item["index"]
        path = study / "attempts" / f"{index:02}" / "result.json"
        if index in (19, 20):
            row = byindex[index]
            if (
                path.exists()
                or (path.parent / "started.json").exists()
                or row.get("status") != "missing"
            ):
                raise ValueError("the two unattempted trials are no longer missing")
            continue
        result = js(path, hashes)
        declared = recorded_input_hash(analysis, f"attempts/{index:02}/result.json")
        if declared != hashes[str(path.resolve())]:
            raise ValueError(f"analysis/result bytes differ at trial{index}")
        if result.get("native_process_started") is not True:
            raise ValueError("actual native start is absent")
        if result.get("protocol_failure") is not (index == 18):
            raise ValueError("protocol status differs from the stopped trial sequence")
        if byindex[index].get("protocol_valid") is not (index != 18):
            raise ValueError("analysis protocol validity differs from retained result")
        if index == 18 and (
            stopped.get("result_sha256") != hashes[str(path.resolve())]
            or result.get("timed_out") is not True
            or result.get("inference_observed") is not False
            or result.get("expected_retrieval_calls") != 0
            or result.get("changed_public_files") != []
            or result.get("telemetry", {}).get("completed_turns") != 0
            or result.get("telemetry", {}).get("token_usage") is not None
        ):
            raise ValueError(
                "timeout evidence no longer matches the explicit no-verified-inference halt"
            )
        if any(
            result.get(key) != item[key] for key in ("index", "task", "repeat", "arm")
        ):
            raise ValueError("native result differs from frozen trial identity")
        if result.get("immutable_files_preserved") is not True:
            raise ValueError("result did not preserve frozen identities")
        checks = result.get("independent", {})
        if any(
            type(checks.get(key, {}).get("passed")) is not bool
            for key in ("focused", "full", "public_contract")
        ):
            raise ValueError("independent checks unavailable")
        success = all(
            checks[key]["passed"] for key in ("focused", "full", "public_contract")
        )
        if (
            result.get("task_success") != success
            or byindex[index].get("independently_verified_success") != success
        ):
            raise ValueError("task outcome differs from independent check evidence")
        usage = result.get("telemetry", {}).get("token_usage")
        metrics = {key: result.get(key) for key in ("cli_wall_ms", "pipeline_wall_ms")}
        metrics.update(
            {
                key: usage.get(key) if isinstance(usage, dict) else None
                for key in ("input_tokens", "cached_input_tokens", "output_tokens")
            }
        )
        if any(
            not finite(metrics[key]) or metrics[key] < 0
            for key in ("cli_wall_ms", "pipeline_wall_ms")
        ):
            raise ValueError("actual timing metrics are invalid")
        token_values = [
            metrics[key]
            for key in ("input_tokens", "cached_input_tokens", "output_tokens")
        ]
        if index == 18:
            if token_values != [None, None, None] or success:
                raise ValueError(
                    "failed trial usage must remain unavailable and failed checks visible"
                )
        elif any(not finite(value) or value < 0 for value in token_values):
            raise ValueError("required valid-trial token metrics are invalid")
        if metrics != byindex[index].get("metrics"):
            raise ValueError("analysis metrics differ from actual result bytes")
        if index != 18 and metrics["cached_input_tokens"] > metrics["input_tokens"]:
            raise ValueError("cached tokens exceed inclusive input")
        results[index] = result
    if (
        len(results) != 18
        or sum(result["protocol_failure"] for result in results.values()) != 1
        or sum(result["task_success"] for result in results.values()) != 17
        or sum(result.get("inference_observed", False) for result in results.values())
        != 9
        or sum(pair["valid"] for pair in analysis.get("pairs", [])) != 13
        or byindex[18].get("status") != "protocol-failed"
    ):
        raise ValueError(
            "actual results do not prove the declared stopped-study counts"
        )
    for index, arm in ((4, "trained-always"), (5, "selective-shadow")):
        result = results[index]
        context = result.get("context", {})
        receipts = result.get("retrieval_receipts", [])
        if (
            result["arm"] != arm
            or result.get("task") != "funcy-first"
            or result.get("repeat") != 1
            or result.get("inference_observed") is not True
            or result.get("observed_receipt_valid") is not True
            or len(receipts) != 1
            or receipts[0].get("inference_observed") is not True
        ):
            raise ValueError(
                "predetermined local-inference demonstration is unavailable"
            )
        receipt = receipts[0]
        required = {
            "arm": arm,
            "model_artifact_digest": plan["model_artifact_digest"],
            "runtime_digest": digest(plan["runtime_files"]),
            "policy_sha256": plan["policy_sha256"],
            "report_sha256": plan["report_sha256"],
            "decision_contract_digest": plan["decision_contract_digest"],
            "request_digest": plan["order"][index - 1]["request_digest"],
            "cli_sha256": plan["runtime_files"]["reflex_cli.py"],
            "source_sha256": plan["order"][index - 1]["mutated_source_sha256"],
        }
        if any(
            receipt.get(key) != value for key, value in required.items()
        ) or receipt.get("context_digest") != digest(context):
            raise ValueError("local-inference receipt identities no longer match")
        if context.get("prediction") != receipt.get("prediction") or receipt.get(
            "prediction_digest"
        ) != digest(context.get("prediction")):
            raise ValueError("local prediction differs from observed receipt")
    proposal, guarded = results[4]["context"], results[5]["context"]
    if (
        proposal["prediction"]["choice"] != "symbol"
        or proposal["choice"] != "symbol"
        or guarded["prediction"]["choice"] != "symbol"
        or guarded["choice"] != "search"
        or guarded.get("advisory", {}).get("fallback") is not True
        or guarded["advisory"].get("candidate_eligible") is not False
    ):
        raise ValueError(
            "actual proposal/fallback evidence does not fit this factual storyboard"
        )
    report = js(study / "shadow-template" / "report.json", hashes)
    policy = js(study / "shadow-template" / "policy.json", hashes)
    if (
        sha(study / "shadow-template" / "report.json") != plan["report_sha256"]
        or sha(study / "shadow-template" / "policy.json") != plan["policy_sha256"]
    ):
        raise ValueError("withheld-policy/report bytes no longer match plan")
    if report.get("deployment_allowed") is not False:
        raise ValueError("this replay requires an actually withheld policy")
    candidates = {}
    for index, arm in ((1, "original-agent"), (4, "trained-always")):
        candidate_path = study / "attempts" / f"{index:02}" / "candidate.py"
        candidate_bytes = read(candidate_path, hashes)
        if hashlib.sha256(candidate_bytes).hexdigest() != results[index].get(
            "candidate_sha256"
        ):
            raise ValueError(
                f"trial{index:02} candidate bytes differ from verified result"
            )
        if results[index]["arm"] != arm or not results[index]["task_success"]:
            raise ValueError(
                f"predetermined trial{index:02} candidate did not pass independent checks"
            )
        candidates[index] = candidate_bytes
    if candidates[1] != candidates[4]:
        raise ValueError(
            "actual trained and baseline repairs differ; revise equal-repair storyboard"
        )
    candidate = candidates[4]
    candidate_lines = candidate.decode().splitlines()
    first = next(
        (
            node
            for node in ast.parse(candidate.decode()).body
            if isinstance(node, ast.FunctionDef) and node.name == "first"
        ),
        None,
    )
    if first is None:
        raise ValueError("actual candidate has no first(seq) function")
    returned = [node for node in first.body if isinstance(node, ast.Return)]
    if len(returned) != 1:
        raise ValueError("candidate repair no longer fits the source excerpt")
    fixed = candidate_lines[returned[0].lineno - 1].strip()
    if fixed != mutation["mutation_before"]:
        raise ValueError(
            "candidate differs from the declared code excerpt; revise storyboard"
        )
    import re

    full_counts = {}
    for index in (1, 4):
        match = re.search(
            r"\b(\d+) passed\b", results[index]["independent"]["full"]["output"]
        )
        if not match:
            raise ValueError(
                f"trial{index:02} actual full-suite pass count unavailable"
            )
        full_counts[index] = int(match.group(1))
    if full_counts[1] != full_counts[4]:
        raise ValueError(
            "baseline and trained full-suite counts differ; revise storyboard"
        )
    full_count = full_counts[4]
    summary = []
    for arm in ARMS:
        group = [
            result
            for result in results.values()
            if result["arm"] == arm and not result["protocol_failure"]
        ]
        planned = sum(item["arm"] == arm for item in plan["order"])
        if planned != 4 or len(group) != (4 if arm in ARMS[:2] else 3):
            raise ValueError("arm completeness differs from the stopped-study evidence")
        summary.append(
            {
                "arm": arm,
                "n": len(group),
                "planned": planned,
                "successes": sum(result["task_success"] for result in group),
                "cli_seconds": statistics.mean(
                    result["cli_wall_ms"] for result in group
                )
                / 1000,
                "pipeline_seconds": statistics.mean(
                    result["pipeline_wall_ms"] for result in group
                )
                / 1000,
                "input_tokens": statistics.mean(
                    result["telemetry"]["token_usage"]["input_tokens"]
                    for result in group
                ),
                "cached_input_tokens": statistics.mean(
                    result["telemetry"]["token_usage"]["cached_input_tokens"]
                    for result in group
                ),
                "output_tokens": statistics.mean(
                    result["telemetry"]["token_usage"]["output_tokens"]
                    for result in group
                ),
            }
        )
    return {
        "hashes": hashes,
        "plan": plan,
        "analysis": analysis,
        "results": results,
        "mutant_line": mutation["mutation_after"],
        "fixed_line": fixed,
        "full_tests": full_count,
        "proposal": proposal,
        "guarded": guarded,
        "arm_summary": summary,
        "total_successes": sum(result["task_success"] for result in results.values()),
        "stopped": stopped,
        "failed_trial": results[18],
        "report": report,
        "policy": policy,
    }


@cache
def font_path(style: str) -> str:
    paths = {
        "regular": (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ),
        "bold": (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        "italic": (
            "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        ),
        "mono": (
            "/System/Library/Fonts/Menlo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ),
    }
    for path in paths[style]:
        if Path(path).is_file():
            return path
    raise RuntimeError(
        f"No local{style} font available; do not download or bundle fonts"
    )


@cache
def font(size: int, style: str = "regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(style), size)


def ease(t: float) -> float:
    return 1 - (1 - min(1.0, max(0.0, t))) ** 3


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    size: int = 24,
    color: str = INK,
    style: str = "regular",
    max_width: int | None = None,
) -> None:
    selected = font(size, style)
    if max_width is not None and draw.textlength(value, font=selected) > max_width:
        raise ValueError(f"Text exceeds its authored box:{value}")
    draw.text(xy, value, fill=color, font=selected)


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    *,
    accent: str = RUST,
    value_size: int = 38,
) -> None:
    draw.rounded_rectangle(box, radius=8, fill="#ebece3", outline=RULE, width=2)
    text(
        draw,
        (box[0] + 22, box[1] + 18),
        label,
        18,
        MUTED,
        max_width=box[2] - box[0] - 44,
    )
    text(
        draw,
        (box[0] + 22, box[1] + 57),
        value,
        value_size,
        accent,
        "bold",
        max_width=box[2] - box[0] - 44,
    )


def code(
    draw: ImageDraw.ImageDraw, y: int, line: str, accent: str, progress: float = 1.0
) -> None:
    draw.rounded_rectangle((58, y, 1222, y + 142), radius=8, fill=INK)
    text(draw, (82, y + 23), "def first(seq):", 26, PAPER, "mono", 1100)
    text(draw, (112, y + 76), line, 25, PAPER, "mono", 1080)
    x = 112 + round(1060 * ease(progress))
    draw.line((112, y + 117, x, y + 117), fill=accent, width=4)


def compact(value: float) -> str:
    return f"{value / 1000:,.1f}k" if value >= 1000 else f"{value:,.0f}"


def frame(t: float, evidence: dict[str, Any]) -> Image.Image:
    """Pure time evaluation: deterministic, no file writes or accumulated state."""
    if not finite(t) or not 0 <= t < SECONDS:
        raise ValueError("frame time must be in the half-open44-second interval")
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    draw.line((58, 92, 1222, 92), fill=RULE, width=2)
    text(draw, (58, 35), "REFLEXFOUNDRY", 27, INK, "bold")
    text(draw, (923, 41), "EVIDENCE REPLAY", 18, RUST, "bold")
    draw.line((58, 642, 1222, 642), fill=RULE, width=2)
    text(
        draw,
        (58, 663),
        "Editorial time. Not a screen recording or real-time speed demonstration.",
        17,
        MUTED,
        max_width=1164,
    )
    if t < 6:
        local = t
        text(draw, (58, 129), "A small bug. A real repair task.", 45, INK, "bold", 1164)
        text(
            draw, (58, 203), "Supplied Funcy mutation / pinned public source", 25, MUTED
        )
        code(draw, 269, evidence["mutant_line"], RUST, (local - 0.5) / 0.9)
        if local > 1.8:
            y = 452 + round(16 * (1 - ease((local - 1.8) / 0.5)))
            text(draw, (58, y), "This skips the first item.", 35, RUST, "italic")
            text(
                draw,
                (58, y + 62),
                "Repair the source. Preserve the unchanged tests.",
                26,
                MUTED,
            )
        text(
            draw,
            (58, 595),
            "The defect was injected for this controlled comparison.",
            20,
            MUTED,
        )
    elif t < 13:
        local = t - 6
        text(draw, (58, 126), "A proposal is not permission.", 45, INK, "bold", 1164)
        text(
            draw,
            (58, 196),
            "Two separate measured trials of the same Funcy request",
            25,
            MUTED,
        )
        card(
            draw,
            (58, 274, 542, 433),
            "TRIAL 04 / TRAINED ALWAYS",
            evidence["proposal"]["prediction"]["choice"].upper(),
        )
        card(
            draw,
            (738, 274, 1222, 433),
            "TRIAL 05 / SELECTIVE SHADOW",
            evidence["guarded"]["choice"].upper(),
            accent=GREEN,
        )
        draw.line((559, 353, 721, 353), fill=RULE, width=3)
        draw.polygon(((721, 353), (709, 346), (709, 360)), fill=GREEN)
        if local >= 0.6:
            x = 559 + 149 * ease((local - 0.6) / 0.8)
            draw.ellipse((x - 6, 347, x + 6, 359), fill=RUST)
        text(draw, (58, 463), "Raw local proposal: symbol", 24, RUST)
        text(draw, (738, 463), "Guarded fallback: search", 24, GREEN)
        text(draw, (58, 511), "Counterfactual read-only choice", 21, MUTED)
        text(draw, (738, 511), "Failed policy stays in shadow", 21, MUTED)
        text(
            draw,
            (58, 587),
            "Actual inference receipts verified. No production policy was activated.",
            22,
            MUTED,
            max_width=1164,
        )
    elif t < 19:
        local = t - 13
        text(draw, (58, 126), "A repair using the local model.", 45, INK, "bold", 1164)
        text(
            draw,
            (58, 196),
            "Trial 04 / actual candidate after verified symbol retrieval",
            25,
            MUTED,
        )
        code(draw, 269, evidence["fixed_line"], GREEN, local / 0.7)
        text(
            draw,
            (58, 458),
            "First item returned. Falsey values preserved.",
            30,
            GREEN,
            "bold",
        )
        text(
            draw,
            (58, 516),
            "Same repair as baseline trial 01; costs compared below.",
            23,
            MUTED,
            max_width=1164,
        )
        text(
            draw,
            (58, 587),
            "Identical code does not establish an efficiency improvement.",
            22,
            MUTED,
        )
    elif t < 25:
        local = t - 19
        text(
            draw,
            (58, 126),
            "Independent checks, after the agent.",
            42,
            INK,
            "bold",
            1164,
        )
        text(
            draw,
            (58, 196),
            "Observer-run validation of trial 04's actual candidate",
            25,
            MUTED,
        )
        checks = (
            ("Focused official test", "PASSED"),
            (f"Full official suite / {evidence['full_tests']} tests", "PASSED"),
            ("Independent public contract", "PASSED"),
        )
        for i, (label, value) in enumerate(checks):
            y = 282 + i * 82
            draw.line((58, y + 61, 1222, y + 61), fill=RULE, width=1)
            text(draw, (58, y), label, 28, INK)
            if local >= 0.35 + i * 0.45:
                offset = round(12 * (1 - ease((local - 0.35 - i * 0.45) / 0.35)))
                text(draw, (1045, y + offset), value, 24, GREEN, "bold")
        text(
            draw,
            (58, 570),
            "Agent-side check execution/order is agent-reported.",
            21,
            MUTED,
        )
        text(
            draw,
            (58, 604),
            "These separate post-run checks are directly observed.",
            21,
            MUTED,
        )
    elif t < 34:
        local = t - 25
        text(
            draw,
            (58, 123),
            "All five arms. An incomplete study.",
            39,
            INK,
            "bold",
            1164,
        )
        text(
            draw,
            (58, 182),
            "18/20 calls / 17 valid / one timeout / two unattempted",
            24,
            MUTED,
        )
        xs = (58, 495, 657, 822, 984, 1132)
        headers = ("POLICY", "VALID / 4", "CLI MEAN", "PIPELINE", "INPUT*", "OUTPUT")
        for x, label in zip(xs, headers):
            text(draw, (x, 245), label, 16, MUTED, "bold")
        for i, (name, row) in enumerate(zip(NAMES, evidence["arm_summary"])):
            y = 286 + i * 54
            draw.line((58, y + 42, 1222, y + 42), fill=RULE, width=1)
            # One column comes into emphasis; all real values remain readable.
            accent = RUST if i == min(4, int(local / 0.65)) and local < 3.25 else INK
            vals = (
                name,
                f"{row['n']}/{row['planned']}",
                f"{row['cli_seconds']:.1f}s",
                f"{row['pipeline_seconds']:.1f}s",
                compact(row["input_tokens"]),
                compact(row["output_tokens"]),
            )
            for j, (x, value) in enumerate(zip(xs, vals)):
                text(
                    draw,
                    (x, y),
                    value,
                    22 if j == 0 else 23,
                    accent,
                    "bold" if j == 0 else "regular",
                    430 if j == 0 else None,
                )
        text(
            draw,
            (58, 582),
            "All valid repairs passed. Means use valid rows only; each arm planned four.",
            20,
            MUTED,
            max_width=1164,
        )
        text(
            draw,
            (58, 612),
            "*Input includes cached subset. Shared baselines; no causal or savings claim.",
            19,
            MUTED,
            max_width=1164,
        )
    else:
        local = t - 34
        offset = round(12 * (1 - ease(local / 0.45)))
        text(draw, (58, 126 + offset), "Timeout. Stop.", 67, INK, "bold", 1164)
        text(
            draw, (58, 212 + offset), "Preserve the evidence.", 62, RUST, "italic", 1164
        )
        text(
            draw,
            (62, 318),
            f"{evidence['total_successes']} repairs passed independent checks. 18 calls started.",
            31,
            INK,
            "bold",
            1160,
        )
        text(
            draw,
            (62, 384),
            "Trial 18: 180-second limit; no verified inference or repair.",
            27,
            MUTED,
            max_width=1160,
        )
        text(
            draw,
            (62, 430),
            "Its token usage is unavailable. Cause unknown.",
            26,
            MUTED,
            max_width=1160,
        )
        text(
            draw,
            (62, 476),
            "Trials 19 and 20 unattempted. Balanced comparison incomplete.",
            27,
            RUST,
            "bold",
            1160,
        )
        text(
            draw,
            (62, 532),
            "The trained policy remains withheld.",
            31,
            GREEN,
            "bold",
            1160,
        )
        text(
            draw,
            (62, 595),
            "Two repositories; correlated repeats. No reliability or superiority claim.",
            21,
            MUTED,
            max_width=1160,
        )
    return image


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def encode(
    evidence: dict[str, Any], output: Path, ffmpeg: str
) -> tuple[Path, list[str]]:
    staging = output / "rendering.mp4"
    cmd = [
        ffmpeg,
        "-n",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(staging),
    ]
    with (output / "ffmpeg.log").open("wb") as log:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=log,
            start_new_session=True,
        )
        assert process.stdin is not None
        os.set_blocking(process.stdin.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdin, selectors.EVENT_WRITE)
        deadline = time.monotonic() + 300
        try:
            for index in range(FPS * SECONDS):
                remaining = memoryview(frame(index / FPS, evidence).tobytes())
                while remaining:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("owned render exceeded300-second bound")
                    if process.poll() is not None:
                        raise RuntimeError(
                            "FFmpeg ended before all frames; inspect ffmpeg.log"
                        )
                    if selector.select(
                        timeout=min(1, max(0, deadline - time.monotonic()))
                    ):
                        try:
                            written = os.write(process.stdin.fileno(), remaining)
                            remaining = remaining[written:]
                        except BlockingIOError:
                            pass
            selector.unregister(process.stdin)
            process.stdin.close()
            if process.wait(timeout=max(1, deadline - time.monotonic())):
                raise RuntimeError("FFmpeg failed; staging bytes preserved")
        except BaseException:
            stop(process)
            raise
        finally:
            selector.close()
    final = output / "reflexfoundry-native-stopped-evidence-replay.mp4"
    staging.rename(final)
    return final, cmd


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--task-source", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="fresh output directory"
    )
    parser.add_argument(
        "--frames-only",
        action="store_true",
        help="validate stopped-study evidence and write poster/diagnostic PNGs without encoding",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; preserve every previous render")
    evidence = load_evidence(
        args.study.resolve(),
        args.analysis.resolve(),
        args.task_source.resolve(),
        args.provenance.resolve(),
    )
    for style in ("regular", "bold", "italic", "mono"):
        font(22, style)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not args.frames_only and (not ffmpeg or not ffprobe):
        parser.error(
            "free local FFmpeg and ffprobe are required; no download is performed"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    frame(36, evidence).resize((960, 540), Image.Resampling.LANCZOS).save(
        args.output / "poster.png"
    )
    diagnostic = args.output / "diagnostic"
    diagnostic.mkdir()
    for t in DIAGNOSTIC_TIMES:
        frame(t, evidence).save(diagnostic / f"frame-{t:05.2f}.png")
    # Prove deterministic non-sequential evaluation, without inferring motion QA.
    before = frame(10.5, evidence).tobytes()
    frame(36, evidence)
    deterministic = before == frame(10.5, evidence).tobytes()
    if not deterministic:
        raise RuntimeError("non-deterministic backward seek")
    video = None
    cmd = None
    probe = None
    if not args.frames_only:
        assert ffmpeg and ffprobe
        video, cmd = encode(evidence, args.output, ffmpeg)
        probe = json.loads(
            subprocess.check_output(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(video),
                ],
                text=True,
                timeout=30,
            )
        )
        streams = probe["streams"]
        if (
            len(streams) != 1
            or streams[0]["codec_type"] != "video"
            or streams[0]["width"] != WIDTH
            or streams[0]["height"] != HEIGHT
            or streams[0]["r_frame_rate"] != "24/1"
            or int(streams[0]["nb_frames"]) != FPS * SECONDS
            or abs(float(probe["format"]["duration"]) - SECONDS) > 0.05
        ):
            raise RuntimeError("encoded media does not match delivery contract")
        subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(video), "-f", "null", "-"],
            check=True,
            capture_output=True,
            timeout=120,
        )
    font_hashes = {
        style: {"path": font_path(style), "sha256": sha(Path(font_path(style)))}
        for style in ("regular", "bold", "italic", "mono")
    }
    manifest = {
        "format": 1,
        "kind": "stopped-study evidence replay, not screen recording",
        "study_status": "stopped-incomplete",
        "planned_trials": 20,
        "native_starts": 18,
        "protocol_valid_trials": 17,
        "failed_trials": [18],
        "unattempted_trials": [19, 20],
        "usage_failed_trial": None,
        "aggregate_means": "Protocol-valid observations only, n=4 for original/heuristic and n=3 for each model arm; not a balanced comparison.",
        "status": "frames-only; unreviewed"
        if args.frames_only
        else "encoded and technically verified; perceptual review pending",
        "duration_seconds": SECONDS,
        "fps": FPS,
        "frame_count": FPS * SECONDS,
        "width": WIDTH,
        "height": HEIGHT,
        "audio": "none",
        "editorial_timing": "Compressed editorial time; animation does not represent actual process speed or measured throughput.",
        "cues": [{"time_seconds": t, "scene": label} for t, label in CUES],
        "source_sha256": sha(Path(__file__)),
        "evidence_sha256": evidence["hashes"],
        "font_sources": font_hashes,
        "video_sha256": sha(video) if video else None,
        "ffmpeg_argv": cmd,
        "ffprobe": probe,
        "diagnostic_sha256": {
            str(p.relative_to(args.output)): sha(p)
            for p in sorted(diagnostic.iterdir())
        },
        "poster_sha256": sha(args.output / "poster.png"),
        "nonsequential_frame_determinism": deterministic,
        "limits": [
            "The study stopped incomplete after trial18 timed out without a validated helper receipt, verified local inference or source repair. An unfinished command may have begun work. Trials19-20 remain unattempted; missing token usage is unavailable, not zero.",
            "Two actual repositories with correlated repeats and shared baselines; descriptive observations only. Unequal arm counts preclude a completed balanced-study claim.",
            "Trial04 proposal, actual candidate and observer-run checks belong to the same trained-assisted trial. Trial05 fallback is a separate shadow observation. Trial01 baseline candidate has identical verified bytes.",
            "Agent-side internal checks are agent-reported; separate observer-run checks are directly observed.",
            "Input counters include cached subset; no monetary, energy, allowance or causal savings claim.",
            "No full-speed perceptual review is claimed by technical verification or diagnostic stills.",
            "No failed policy became deployable; production deployment remains withheld.",
        ],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "video": str(video) if video else None,
                "status": manifest["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
