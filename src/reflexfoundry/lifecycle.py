"""Fail-closed advisory lifecycle. Permissions and execution remain with the agent.

The local JSON store serializes writers. It is evidence bookkeeping, not a trust
boundary against a user deliberately rewriting their own evaluation or state.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from .core import (
    SPECS,
    digest,
    discover,
    privacy_filter,
    read_json,
    read_records,
    validate_inputs,
    write_json,
)
from .core import (
    finite_number as _number,
)
from .evaluation import choose
from .model import LocalPolicy, artifact_digest, file_hash


@contextlib.contextmanager
def locked(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".lock"
    fd = None
    for _ in range(100):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            time.sleep(0.02)
    if fd is None:
        raise RuntimeError("workspace busy; retry, or inspect a stale .lock after its owner exits")
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink()


def vocabulary(records: list[dict[str, Any]]) -> list[str]:
    return sorted({w for row in records for w in re.findall(r"[a-zA-Z_]{3,}",
        json.dumps(row["inputs"]).lower())})


def outside_domain(inputs: dict[str, Any], words: list[str]) -> bool:
    """Conservative vocabulary shift proxy, not a statistical drift guarantee."""
    tokens = set(re.findall(r"[a-zA-Z_]{3,}", json.dumps(inputs).lower()))
    return not words or len(tokens - set(words)) / max(1, len(tokens)) > 0.45


def register(root: Path, model: Path, report: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    if report["dataset_digest"] != digest(records):
        raise ValueError("evaluation dataset does not match")
    if report["spec"] not in SPECS or not isinstance(report.get("deployment_allowed"), bool):
        raise ValueError("unsupported evaluation report")
    if report["model_digest"] != file_hash(model / "model.safetensors"):
        raise ValueError("evaluation model does not match")
    if report.get("artifact_digest", artifact_digest(model)) != artifact_digest(model):
        raise ValueError("evaluated inference artifacts do not match")
    threshold = report["calibration"]["threshold"]
    if not _number(threshold) or not 0 <= threshold <= 1.01:
        raise ValueError("invalid calibrated threshold")
    manifest = read_json(model / "manifest.json", {})
    training = [r for r in records if r["split"] == "train"]
    if manifest.get("train_digest") != digest(training):
        raise ValueError("training provenance does not match evaluation training data")
    if manifest.get("weights_sha256") != report["model_digest"]:
        raise ValueError("training model bytes do not match evaluated artifact")
    catalog = digest([s.__dict__ for s in SPECS.values()])
    if manifest.get("spec_catalog_digest", catalog) != catalog:
        raise ValueError("model was trained against a different decision catalog")
    actual_artifacts = artifact_digest(model)
    if report.get("artifact_digest", actual_artifacts) != actual_artifacts:
        raise ValueError("evaluated inference artifacts changed before registration")
    policy = {"id": report["model_digest"][:12], "model": str(model.resolve()),
        "model_digest": report["model_digest"], "artifact_digest": artifact_digest(model),
        "report_digest": digest(report), "dataset_digest": digest(records),
        "report": report, "spec": report["spec"], "spec_digest": digest(SPECS[report["spec"]].__dict__),
        "vocabulary": vocabulary([r for r in records if r["split"] == "train"]),
        "training_records": manifest.get("training_records", len(training)), "status": "evaluated"}
    with locked(root):
        write_json(root / "policy.json", policy)
        write_json(root / "report.json", report)
        # A new registration never inherits the previous deployment permission.
        previous = read_json(root / "deployment.json", {"mode": "off", "history": []})
        _revert(root, previous, "policy registered; shadow validation required")
    return policy


def _revert(root: Path, deployment: dict[str, Any], reason: str) -> None:
    previous = deployment.get("mode", "off")
    deployment.setdefault("history", []).append({"time": time.time(), "from": previous,
        "to": "off", "reason": reason, "policy": deployment.get("policy")})
    deployment["history"] = deployment["history"][-1000:]
    deployment["mode"] = "off"
    deployment["reason"] = reason
    write_json(root / "deployment.json", deployment)


def _binding_valid(policy: dict[str, Any], spec_id: str) -> bool:
    return (policy.get("spec") == spec_id
        and policy.get("spec_digest") == digest(SPECS[spec_id].__dict__)
        and policy.get("report_digest") == digest(policy["report"])
        and policy.get("artifact_digest") == artifact_digest(Path(policy["model"])))


def transition(root: Path, mode: str, opt_in: bool = False, max_decisions: int = 100) -> dict[str, Any]:
    if mode not in {"shadow", "deploy", "rollback"}:
        raise ValueError("unsupported transition")
    if isinstance(max_decisions, bool) or not isinstance(max_decisions, int) or not 1 <= max_decisions <= 10000:
        raise ValueError("max_decisions must be an integer from 1 to 10000")
    with locked(root):
        policy = read_json(root / "policy.json")
        if not policy:
            raise ValueError("evaluate and register a policy first")
        old = read_json(root / "deployment.json", {"mode": "off", "history": []})
        if mode == "deploy":
            if not opt_in:
                raise ValueError("bounded deployment requires --opt-in")
            if not policy["report"]["deployment_allowed"] or not _binding_valid(policy, policy["spec"]):
                raise ValueError("deployment blocked by evaluation or changed artifacts")
            if old.get("policy") != policy["id"] or old["mode"] != "shadow":
                raise ValueError("this policy must first run in shadow mode")
            verified = [r for r in read_json(root / "requests.json", [])
                        if r.get("policy") == policy["id"] and r.get("report_digest") == policy["report_digest"]
                        and r.get("mode") == "shadow" and r.get("deployment_epoch") == old.get("epoch")
                        and r.get("abstained") is False and r.get("candidate_eligible") is True
                        and r.get("candidate_verified") is True and "success" in r]
            distinct = {r["input_digest"] for r in verified
                        if isinstance(r.get("input_digest"), str) and r["input_digest"]}
            if len(distinct) < 30 or any(not r["success"] for r in verified):
                raise ValueError("need 30 verified shadow outcomes from distinct inputs with no regression before opt-in")
        next_mode = "deployed" if mode == "deploy" else "off" if mode == "rollback" else "shadow"
        event = {"time": time.time(), "from": old["mode"], "to": next_mode, "policy": policy["id"],
                 "reason": "explicit " + mode}
        state = {"mode": next_mode, "policy": policy["id"], "history": (old["history"] + [event])[-1000:],
                 "max_decisions": max_decisions, "decisions": 0, "epoch": uuid.uuid4().hex}
        write_json(root / "deployment.json", state)
        return state


def _prediction(value: Any, spec_id: str) -> dict[str, Any]:
    if (not isinstance(value, dict) or value.get("choice") not in SPECS[spec_id].choices
            or not _number(value.get("confidence")) or not 0 <= value["confidence"] <= 1
            or not _number(value.get("duration_ms")) or value["duration_ms"] < 0
            or not isinstance(value.get("stable"), bool) or not isinstance(value.get("truncated"), bool)):
        raise ValueError("invalid local prediction")
    # Do not persist arbitrary backend fields or exception text.
    return {key: value[key] for key in ("choice", "confidence", "duration_ms", "stable", "truncated")}


def decide(root: Path, spec_id: str, inputs: dict[str, Any], backend: str = "auto") -> dict[str, Any]:
    inputs = privacy_filter(validate_inputs(spec_id, inputs))
    spec = SPECS[spec_id]
    # An inactive advisory request is a read-only operation, including in native
    # agent sandboxes. Never create bookkeeping merely to return a fallback.
    initial = read_json(root / "deployment.json", {"mode": "off"})
    if initial.get("mode") == "off" or not (root / "policy.json").exists():
        return {"request_id": uuid.uuid4().hex, "spec": spec_id, "choice": spec.fallback,
                "fallback": True, "mode": "off", "reason": "no active policy", "advisory": True}
    decision_started = time.perf_counter()
    with locked(root):
        policy = read_json(root / "policy.json")
        deployment = read_json(root / "deployment.json", {"mode": "off", "history": []})
        result: dict[str, Any] = {"request_id": uuid.uuid4().hex, "spec": spec_id,
            "choice": spec.fallback, "fallback": True, "mode": deployment["mode"],
            "reason": "no active policy", "advisory": True, "input_digest": digest(inputs)}
        if not policy or deployment["mode"] == "off":
            return result
        result.update({"policy": policy["id"], "report_digest": policy["report_digest"],
                       "deployment_epoch": deployment.get("epoch")})
        requests = read_json(root / "requests.json", [])
        try:
            if not _binding_valid(policy, spec_id) or deployment.get("policy") != policy["id"]:
                raise ValueError("policy artifacts or candidate catalog changed")
            if deployment["mode"] == "deployed" and deployment.get("decisions", 0) >= deployment["max_decisions"]:
                result["reason"] = "bounded deployment exhausted"
                _revert(root, deployment, result["reason"])
            elif outside_domain(inputs, policy["vocabulary"]):
                result["reason"] = "input distribution drift"
                _revert(root, deployment, result["reason"])
            else:
                runtime = LocalPolicy(Path(policy["model"]), backend)
                prediction = _prediction(runtime.predict(spec_id, inputs), spec_id)
                # Each CLI invocation cold-starts; both real elapsed and reported
                # model startup are charged before advisory delegation is allowed.
                startup = runtime.startup_ms
                if not _number(startup) or startup < 0:
                    raise ValueError("invalid startup cost")
                prediction["duration_ms"] = max(prediction["duration_ms"] + startup,
                    (time.perf_counter() - decision_started) * 1000)
                candidate, fallback = choose(prediction, spec_id, policy["report"]["calibration"]["threshold"])
                result.update({"prediction": prediction, "candidate": candidate, "candidate_eligible": not fallback, "abstained": fallback,
                    "reason": "shadow observation" if deployment["mode"] == "shadow" else "selective decision",
                    "fallback": fallback or deployment["mode"] != "deployed",
                    "choice": candidate if deployment["mode"] == "deployed" else spec.fallback})
                if deployment["mode"] == "deployed":
                    deployment["decisions"] = deployment.get("decisions", 0) + 1
                    write_json(root / "deployment.json", deployment)
                recent = [r for r in requests if r.get("policy") == policy["id"]
                          and r.get("report_digest") == policy["report_digest"]
                          and r.get("deployment_epoch") == deployment.get("epoch")][-19:] + [result]
                if len(recent) == 20 and sum(r.get("abstained", True) for r in recent) >= 10:
                    result.update({"choice": spec.fallback, "fallback": True,
                                   "reason": "sustained abstention indicates uncertainty or drift"})
                    _revert(root, deployment, result["reason"])
        except Exception as exc:
            result["reason"] = "local policy unavailable or changed: " + type(exc).__name__
            _revert(root, deployment, result["reason"])
        requests.append(result)
        write_json(root / "requests.json", requests[-10000:])
        return result


def outcome(root: Path, request_id: str, success: bool, duration_ms: float, candidate_verified: bool = False) -> dict[str, Any]:
    if (not isinstance(success, bool) or not isinstance(candidate_verified, bool)
            or not _number(duration_ms) or duration_ms < 0):
        raise ValueError("outcome requires boolean success and finite nonnegative duration_ms")
    with locked(root):
        requests = read_json(root / "requests.json", [])
        matches = [r for r in requests if r["request_id"] == request_id]
        if not matches:
            raise ValueError("unknown request; outcomes must refer to an actual observed decision")
        request = matches[0]
        if "success" in request:
            raise ValueError("outcome already recorded")
        if candidate_verified and not request.get("candidate_eligible"):
            raise ValueError("no eligible learned candidate exists to verify")
        request.update({"success": success, "outcome_ms": duration_ms, "candidate_verified": candidate_verified})
        write_json(root / "requests.json", requests)
        deployment = read_json(root / "deployment.json", {"mode": "off", "history": []})
        if not success and deployment["mode"] in {"deployed", "shadow"} and request.get("policy") == deployment.get("policy"):
            _revert(root, deployment, "verified outcome regression")
        return {"request": request, "deployment": deployment}


def state(root: Path) -> dict[str, Any]:
    rows = read_records(root / "records.jsonl")
    policy = read_json(root / "policy.json")
    deployment = read_json(root / "deployment.json")
    return {"records": rows, "discoveries": discover(rows), "policies": [policy] if policy else [],
        "deployments": [deployment] if deployment else [], "report": read_json(root / "report.json"),
        "requests": read_json(root / "requests.json", [])}
