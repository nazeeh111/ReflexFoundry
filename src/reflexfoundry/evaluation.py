"""Held-out outcome and cost evaluation. Test data never chooses thresholds."""
from __future__ import annotations

import math
import random
import statistics
from typing import Any

from .core import SPECS, digest, validate_splits


def wilson_upper(errors: int, n: int) -> float:
    if not n:
        return 1.0
    z = 1.96
    p = errors / n
    return (p + z*z/(2*n) + z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)


def interval(values: list[float], seed: int = 17) -> list[float]:
    """Paired task bootstrap, not independent per-policy error bars."""
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(1000))
    return [means[24], means[974]]


def choose(prediction: dict[str, Any], spec_id: str, threshold: float,
           budget_ms: float | None = None) -> tuple[str, bool]:
    spec = SPECS[spec_id]
    confidence: Any = prediction.get("confidence")
    elapsed: Any = prediction.get("duration_ms")
    def numeric(x: Any) -> bool:
        return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)
    valid = (prediction.get("choice") in spec.choices and prediction.get("stable") is True
             and prediction.get("truncated") is False and numeric(confidence)
             and 0 <= confidence <= 1 and confidence >= threshold and numeric(elapsed)
             and 0 <= elapsed <= (budget_ms if budget_ms is not None else spec.budget_ms))
    return (prediction["choice"], False) if valid else (spec.fallback, True)


def calibrate(rows: list[dict[str, Any]], predictions: dict[str, dict[str, Any]],
              max_error: float = 0.10, min_n: int = 30) -> dict[str, Any]:
    """Threshold search is exploratory calibration; independent promotion validates it."""
    if not 0 < max_error < 1 or min_n < 1:
        raise ValueError("invalid calibration risk or minimum sample count")
    if any(r["split"] != "calibration" for r in rows):
        raise ValueError("calibration accepts calibration split only")
    candidates = []
    for threshold in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]:
        accepted = []
        errors = 0
        for row in rows:
            choice, fallback = choose(predictions[row["id"]], row["spec"], threshold)
            if not fallback:
                accepted.append(row)
                errors += int(not row["outcomes"][choice]["success"])
        upper = wilson_upper(errors, len(accepted))
        candidates.append({"threshold": threshold, "accepted": len(accepted),
                           "errors": errors, "error_upper_95": upper})
    eligible = [c for c in candidates if c["accepted"] >= min_n and c["error_upper_95"] <= max_error]
    selected = max(eligible, key=lambda c: (c["accepted"], -c["threshold"])) if eligible else None
    return {"threshold": selected["threshold"] if selected else 1.01,
        "max_error": max_error, "min_n": min_n, "candidates": candidates,
        "eligible": selected is not None, "calibration_digest": digest(rows),
        "note": "Threshold search uses calibration only; confidence bounds here are descriptive after search."}


def heuristic(row: dict[str, Any]) -> str:
    from .benchmark import heuristic as baseline
    return baseline(row["inputs"])


def summarize(rows: list[dict[str, Any]], predictions: dict[str, dict[str, Any]],
              threshold: float, startup_ms: float,
              base_predictions: dict[str, dict[str, Any]] | None = None,
              base_startup_ms: float = 0.0) -> dict[str, Any]:
    policies: dict[str, list[dict[str, Any]]] = {name: [] for name in
        ("original-full", "deterministic-heuristic", "always-focused", "trained-always", "selective")}
    if base_predictions:
        policies["ordinary-laya"] = []
    details = []
    for row in rows:
        prediction = predictions[row["id"]]
        cold_prediction = dict(prediction, duration_ms=prediction["duration_ms"] + startup_ms)
        selective, fallback = choose(cold_prediction, row["spec"], threshold)
        choices = {"original-full": "full", "deterministic-heuristic": heuristic(row),
            "always-focused": "focused", "trained-always": prediction["choice"], "selective": selective}
        if base_predictions:
            choices["ordinary-laya"] = base_predictions[row["id"]]["choice"]
        entry = {"id": row["id"], "prediction": prediction, "selected": selective,
                 "fallback": fallback, "outcomes": row["outcomes"]}
        details.append(entry)
        for name, choice in choices.items():
            outcome = row["outcomes"][choice]
            overhead = prediction["duration_ms"] + startup_ms if name in {"trained-always", "selective"} else 0.0
            if name == "ordinary-laya" and base_predictions:
                overhead = base_predictions[row["id"]]["duration_ms"] + base_startup_ms
            policies[name].append({"success": outcome["success"],
                "ms": outcome["duration_ms"] + overhead,
                "fallback": fallback if name == "selective" else False,
                "choice": choice})
    summaries = []
    n = len(rows)
    for name, observations in policies.items():
        startup = startup_ms if name in {"trained-always", "selective"} else base_startup_ms if name == "ordinary-laya" else 0
        total = sum(o["ms"] for o in observations)
        errors = sum(not o["success"] for o in observations)
        summaries.append({"name": name, "n": n, "success_rate": 1 - errors / max(1, n),
            "errors": errors, "error_upper_95": wilson_upper(errors, n),
            "total_ms": total, "mean_ms": total / max(1, n), "startup_ms": startup,
            "fallback_rate": sum(o["fallback"] for o in observations) / max(1, n),
            "decision_counts": {c: sum(o["choice"] == c for o in observations) for c in ("focused", "full")}})
    baseline = policies["original-full"]
    selective_rows = policies["selective"]
    paired_saved = [a["ms"] - b["ms"]
                    for a, b in zip(baseline, selective_rows)]
    successes = [float(b["success"]) - float(a["success"]) for a, b in zip(baseline, selective_rows)]
    # Repository is the sampling unit, not each timing repeat or related patch.
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(row["repository"], []).append(index)
    saved_groups = [statistics.mean(paired_saved[i] for i in indexes) for indexes in groups.values()]
    success_groups = [statistics.mean(successes[i] for i in indexes) for indexes in groups.values()]
    accepted = [r for r in details if not r["fallback"]]
    accepted_errors = sum(not r["outcomes"][r["selected"]]["success"] for r in accepted)
    accepted_by_repo: dict[str, list[bool]] = {}
    for row, detail in zip(rows, details):
        if not detail["fallback"]:
            accepted_by_repo.setdefault(row["repository"], []).append(not detail["outcomes"][detail["selected"]]["success"])
    cluster_errors = sum(any(values) for values in accepted_by_repo.values())
    agreement = [predictions[row["id"]]["choice"] == row["selected"] for row in rows]
    confidences = [predictions[row["id"]]["confidence"] for row in rows]
    ece = 0.0
    for b in range(10):
        indexes = [i for i, c in enumerate(confidences) if b/10 <= c <= (b+1)/10 and (b == 0 or c > b/10)]
        if indexes:
            ece += len(indexes) / max(1, n) * abs(statistics.mean(confidences[i] for i in indexes) - statistics.mean(agreement[i] for i in indexes))
    return {"policies": summaries, "details": details,
        "decision_label_agreement": statistics.mean(agreement) if agreement else None,
        "decision_ece_10_bins": ece,
        "confidence_brier": statistics.mean((float(correct) - confidence)**2 for correct, confidence in zip(agreement, confidences)) if agreement else None,
        "decision_metric_note": "Agreement with fastest safe observed choice is diagnostic only; it is not task success or a population calibration guarantee.",
        "paired_saved_ms_95": interval(saved_groups), "paired_success_delta_95": interval(success_groups),
        "repository_groups": len(groups),
        "accepted": len(accepted), "accepted_errors": accepted_errors,
        "accepted_error_upper_95": wilson_upper(accepted_errors, len(accepted)),
        "accepted_repositories": len(accepted_by_repo),
        "accepted_repository_error_upper_95": wilson_upper(cluster_errors, len(accepted_by_repo)),
        "order_flip_rate": sum(not p["stable"] for p in (predictions[r["id"]] for r in rows)) / max(1, n),
        "unnecessary_fallback": sum(r["fallback"] and r["outcomes"][r["prediction"]["choice"]]["success"] for r in details),
        "wrong_decisions": [r["id"] for r in details if not r["outcomes"][r["selected"]]["success"]]}


def evaluate(records: list[dict[str, Any]], predictions: dict[str, dict[str, Any]],
             startup_ms: float, model_digest: str,
             base_predictions: dict[str, dict[str, Any]] | None = None,
             base_startup_ms: float = 0.0) -> dict[str, Any]:
    validate_splits(records)
    if any(r["spec"] != "test-scope-v1" for r in records):
        raise ValueError("executed evaluator currently supports test-scope-v1 only")
    parts = {s: [r for r in records if r["split"] == s] for s in ("calibration", "promotion", "test")}
    if any(len(rows) < 30 for rows in parts.values()):
        raise ValueError("at least 30 independent tasks in each evaluation split are required")
    cold_predictions = {key: dict(value, duration_ms=value["duration_ms"] + startup_ms) for key, value in predictions.items()}
    calibration = calibrate(parts["calibration"], cold_predictions)
    promotion = summarize(parts["promotion"], predictions, calibration["threshold"], startup_ms,
                          base_predictions, base_startup_ms)
    test = summarize(parts["test"], predictions, calibration["threshold"], startup_ms,
                     base_predictions, base_startup_ms)
    reasons = []
    if not calibration["eligible"]:
        reasons.append("calibration has insufficient safe delegation evidence")
    if promotion["accepted_repositories"] < 30 or promotion["accepted"] < 30 or promotion["accepted_repository_error_upper_95"] > calibration["max_error"]:
        reasons.append("independent promotion accepted-risk bound failed")
    if promotion["paired_success_delta_95"][0] < 0:
        reasons.append("promotion task outcomes regress")
    if promotion["paired_saved_ms_95"][0] <= 0:
        reasons.append("promotion has no reliable net time improvement including startup")
    metrics = {r["name"]: r for r in promotion["policies"]}
    if metrics["selective"]["total_ms"] >= metrics["deterministic-heuristic"]["total_ms"] and metrics["deterministic-heuristic"]["success_rate"] >= metrics["selective"]["success_rate"]:
        reasons.append("simple heuristic dominates the candidate")
    if metrics["selective"]["success_rate"] < metrics["deterministic-heuristic"]["success_rate"]:
        reasons.append("candidate task outcomes regress against the deterministic heuristic")
    # Locked test is a final safety veto, never a threshold search or model selection signal.
    if test["paired_success_delta_95"][0] < 0 or test["paired_saved_ms_95"][0] <= 0:
        reasons.append("locked test does not confirm outcome and time benefit")
    test_metrics = {row["name"]: row for row in test["policies"]}
    if test_metrics["selective"]["success_rate"] < test_metrics["deterministic-heuristic"]["success_rate"]:
        reasons.append("locked test task outcomes regress against the deterministic heuristic")
    return {"format": 1, "spec": "test-scope-v1", "dataset_digest": digest(records),
        "model_digest": model_digest, "calibration": calibration, "promotion": promotion,
        "test": test, "policies": test["policies"], "deployment_allowed": not reasons,
        "reasons": reasons, "currency_cost": None,
        "scope": "Generated coding-change validation fixtures, not autonomous agent task success.",
        "execution_contract": "Cold CLI: measured startup charged on every decision; warm throughput is diagnostic only.",
        "statistics": "Repository-group paired bootstrap 1000 resamples; per-task Wilson bounds descriptive under shared fixture grammar."}
