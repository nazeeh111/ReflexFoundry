"""A fixed, local-teacher imitation ablation. No native agent or network calls.

Run with PYTHONPATH=src. New output directories only. Model artifacts remain in
the disposable study workspace; compact evidence can be exported for review.
"""
from __future__ import annotations

import argparse
import copy
import gc
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from reflexfoundry.core import (
    SPECS,
    decision_contract_digest,
    digest,
    read_json,
    read_records,
    validate_splits,
    write_json,
)
from reflexfoundry.evaluation import evaluate
from reflexfoundry.model import LocalPolicy, artifact_digest, file_hash, train, training_examples

ARMS = ("outcome", "imitation")
RECIPE: dict[str, Any] = {"epochs": 4, "seed": 17, "micro_batch": 4, "grad_accum": 1,
          "head_lr": 1e-4, "freeze_encoder": True, "loss": "soft-ce",
          "shuffle_options": ["choice"], "calib_frac": 0.15,
          "calib_seed": 20260922, "max_len": 256}


def eligible_training(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validate_splits(records, require_evaluation_outcomes=True)
    if {row["spec"] for row in records} != {"context-route-v1"}:
        raise ValueError("the preregistered experiment is context-route-v1 only")
    return [row for row in records if row["split"] == "train"
            and any(outcome["success"] for outcome in row["outcomes"].values())]


def input_identity(records: list[dict[str, Any]]) -> str:
    return digest([{key: row.get(key) for key in ("id", "repository", "task_group", "split", "spec", "inputs")}
                   for row in records])


def arm_records(records: list[dict[str, Any]], teacher: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    eligible = eligible_training(records)
    if set(teacher) != {row["id"] for row in eligible}:
        raise ValueError("teacher labels must cover exactly the shared eligible training cohort")
    labels = {}
    for row in eligible:
        choice = teacher[row["id"]].get("choice")
        if choice not in SPECS[row["spec"]].choices:
            raise ValueError("invalid canonical teacher label")
        # Do not discard order-unstable teacher predictions. The canonical choice
        # is the fixed teacher target; reversed order remains a diagnostic.
        labels[row["id"]] = training_examples([row])[0][0]["expected"]["decision"]
    result: dict[str, list[dict[str, Any]]] = {}
    for arm in ARMS:
        rows = []
        for original in records:
            if original["split"] == "train" and original["id"] not in labels:
                continue
            row = copy.deepcopy(original)
            if row["split"] == "train":
                row.pop("outcomes")
                row["selected"] = labels[row["id"]] if arm == "outcome" else teacher[row["id"]]["choice"]
            rows.append(row)
        validate_splits(rows, require_evaluation_outcomes=True)
        result[arm] = rows
    if input_identity(result["outcome"]) != input_identity(result["imitation"]):
        raise ValueError("arm inputs differ")
    for split in ("calibration", "promotion", "test"):
        if ([r for r in result["outcome"] if r["split"] == split]
                != [r for r in result["imitation"] if r["split"] == split]):
            raise ValueError("held-out evidence differs between arms")
    return result


def jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows))


def reclaim() -> None:
    gc.collect()
    import mlx.core as mx
    import torch
    torch.mps.empty_cache()
    mx.clear_cache()


def probe(model: Path) -> dict[str, Any]:
    start = time.perf_counter()
    identity = artifact_digest(model)
    screening = (time.perf_counter() - start) * 1000
    policy = LocalPolicy(model, "mlx")
    return {"artifact_digest": identity, "screening_ms": screening,
            "model_startup_ms": policy.startup_ms,
            "accounted_startup_ms": screening + policy.startup_ms}


def run(records_path: Path, base: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("choose a fresh output directory")
    output.mkdir(parents=True)
    records = read_records(records_path)
    eligible = eligible_training(records)
    if len(eligible) != 36:
        raise ValueError("preregistered shared cohort must contain exactly 36 usable rows")
    from laya.train import split_calibration
    optimization, calibration = split_calibration(eligible, 400, RECIPE["calib_frac"], RECIPE["calib_seed"])
    manifest = {"study": "local-teacher-imitation-context-v1", "source_records_sha256": file_hash(records_path),
        "source_records_digest": digest(records), "decision_contract_digest": decision_contract_digest(),
        "base_artifact_digest": artifact_digest(base), "base_weights_sha256": file_hash(base / "model.safetensors"),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runner_sha256": file_hash(Path(__file__)), "recipe": RECIPE,
        "native_training_source_sha256": file_hash(Path(str(importlib.metadata.distribution("laya").locate_file("laya/train.py")))),
        "training_available": sum(row["split"] == "train" for row in records),
        "shared_eligible_ids": [row["id"] for row in eligible],
        "optimization_ids": [row["id"] for row in optimization],
        "internal_calibration_ids": [row["id"] for row in calibration],
        "excluded_ids": [row["id"] for row in records if row["split"] == "train" and row not in eligible],
        "training_order": list(ARMS), "evaluation_order": "alternate arms for each shared held-out record",
        "startup_probe_order": [list(ARMS), list(reversed(ARMS)), list(ARMS)],
        "python": sys.version, "platform": platform.platform(),
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ("laya", "laya-mlx", "torch", "transformers", "mlx", "numpy", "safetensors")},
        "limits": ["One fixed seed and fit per arm; no model selection or retuning after test.",
            "The shared cohort was selected using measured outcome eligibility in both arms; this controls labels, not data acquisition.",
            "Teacher is an untuned local Laya checkpoint, not the original Codex agent.",
            "One actual repository per split; correlated queries and tiny internal calibration prevent broad inference.",
            "Source retrieval coverage outcomes do not establish autonomous coding success.",
            "Stage costs are retrospective recorded action time plus measured library load/screening/inference, not full CLI wall time.",
            "Startup probes use fresh Python processes but share operating-system caches. Concurrent host load is uncontrolled."]}
    write_json(output / "plan.json", manifest)
    teacher_start = time.perf_counter()
    teacher_runtime = LocalPolicy(base, "mlx")
    teacher = {row["id"]: teacher_runtime.predict(row["spec"], row["inputs"]) for row in eligible}
    teacher_ms = (time.perf_counter() - teacher_start) * 1000
    write_json(output / "teacher-training-predictions.json", teacher)
    del teacher_runtime
    reclaim()
    datasets = arm_records(records, teacher)
    label_report: dict[str, Any] = {"shared_input_digest": input_identity(datasets["outcome"]),
        "teacher_generation_ms": teacher_ms, "teacher_order_unstable": sum(not p["stable"] for p in teacher.values()),
        "label_disagreements": [a["id"] for a, b in zip(datasets["outcome"], datasets["imitation"])
                                if a["split"] == "train" and a["selected"] != b["selected"]],
        "label_counts": {arm: dict(Counter(row["selected"] for row in rows if row["split"] == "train"))
                         for arm, rows in datasets.items()}}
    write_json(output / "labels.json", label_report)
    for arm in ARMS:
        jsonl(output / f"records-{arm}.jsonl", datasets[arm])
        model = output / f"model-{arm}"
        trained = train(datasets[arm], base, model, epochs=RECIPE["epochs"], device="mps")
        actual_recipe = trained["summary"]["train_report"]["training"]
        if any(json.loads(json.dumps(actual_recipe[key])) != value for key, value in RECIPE.items()):
            raise ValueError("upstream training recipe changed")
        if (trained["summary"]["train_items"] != len(optimization)
                or trained["summary"]["calibration_items"] != len(calibration)):
            raise ValueError("upstream internal cohort split changed")
        write_json(output / f"training-{arm}.json", trained)
        reclaim()
    if artifact_digest(base) != manifest["base_artifact_digest"]:
        raise ValueError("base artifact changed during teacher generation/training")
    probes: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    for order in manifest["startup_probe_order"]:
        for arm in order:
            model = output / f"model-{arm}"
            observed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "probe", str(model)],
                                      check=True, capture_output=True, text=True, timeout=120)
            probes[arm].append(json.loads(observed.stdout))
    write_json(output / "startup-probes.json", probes)
    policies = {arm: LocalPolicy(output / f"model-{arm}", "mlx") for arm in ARMS}
    identities = {arm: artifact_digest(output / f"model-{arm}") for arm in ARMS}
    predictions: dict[str, dict[str, Any]] = {arm: {} for arm in ARMS}
    for i, row in enumerate(r for r in records if r["split"] != "train"):
        for arm in ARMS if i % 2 == 0 else tuple(reversed(ARMS)):
            predictions[arm][row["id"]] = policies[arm].predict(row["spec"], row["inputs"])
    write_json(output / "heldout-predictions.json", predictions)
    summary: dict[str, Any] = {"status": "executed", "plan_digest": digest(manifest),
        "labels": label_report, "arms": {}, "deployment": "withheld", "native_agent_calls": 0,
        "paid_api_calls": 0, "limits": manifest["limits"]}
    for arm in ARMS:
        model = output / f"model-{arm}"
        if artifact_digest(model) != identities[arm]:
            raise ValueError("trained inference artifacts changed during scoring")
        if any(p["artifact_digest"] != identities[arm] for p in probes[arm]):
            raise ValueError("startup probes did not use evaluated model")
        startup = statistics.median(p["accounted_startup_ms"] for p in probes[arm])
        report = evaluate(datasets[arm], predictions[arm], startup, file_hash(model / "model.safetensors"))
        report["execution_contract"] = "Retrospective retrieval-stage accounting: recorded action time plus measured local library startup, integrity screening and per-row inference. Complete CLI/interpreter/import/process time is not measured."
        report["artifact_digest"] = identities[arm]
        report["screening_and_load_source"] = "median of three fresh-process local startup probes"
        write_json(output / f"evaluation-{arm}.json", report)
        summary["arms"][arm] = {"model_weights_sha256": report["model_digest"],
            "model_artifact_digest": identities[arm], "test": report["test"],
            "deployment_allowed": report["deployment_allowed"], "reasons": report["reasons"],
            "training_ms": read_json(output / f"training-{arm}.json")["training_ms"],
            "median_screening_and_load_ms": startup}
    if decision_contract_digest() != manifest["decision_contract_digest"]:
        raise ValueError("decision contract changed during study")
    del policies
    reclaim()
    write_json(output / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "labels": label_report,
                      "deployment_allowed": {a: summary["arms"][a]["deployment_allowed"] for a in ARMS}}), flush=True)


def main() -> None:
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise ValueError("run with HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run")
    command.add_argument("--records", type=Path, required=True)
    command.add_argument("--base", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("probe")
    command.add_argument("model", type=Path)
    args = parser.parse_args()
    if args.command == "probe":
        print(json.dumps(probe(args.model)))
    else:
        run(args.records, args.base, args.output)


if __name__ == "__main__":
    main()
