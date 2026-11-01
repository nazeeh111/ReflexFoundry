"""Fixed five-arm public-source retrieval, copied into a prepared native case.

No Codex invocation or policy deployment occurs here. The trained-always arm is
an explicitly declared read-only counterfactual, not activation of a failed
policy. The stdout receipt is observable evidence, not cryptographic attestation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ARMS = ("original-search", "deterministic-heuristic", "ordinary-laya", "trained-always", "selective-shadow")
RECEIPT_KEY = "reflexfoundry_native_receipt"


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def require_clean_runtime(root: Path) -> None:
    """Reject executable caches before importing any prepared runtime module.

    Python's -B prevents writes, not reads of an existing matching .pyc file.
    Trusted dependency caches outside this frozen runtime are unaffected.
    """
    if not root.is_dir() or root.is_symlink():
        raise ValueError("prepared runtime must be a real directory")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("runtime files must not be links")
        if path.suffix.lower() in {".pyc", ".pyo"}:
            raise ValueError("prepared runtime bytecode caches are forbidden")
        if path.name == "__pycache__" and path.is_dir() and any(path.iterdir()):
            raise ValueError("nonempty prepared runtime __pycache__ is forbidden")


def runtime_inventory(root: Path) -> dict[str, str]:
    require_clean_runtime(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("runtime files must not be links")
        if path.is_file():
            result[str(path.relative_to(root))] = sha(path)
    return result


def prediction(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("choice") not in {"symbol", "search"}:
        return None
    for key in ("confidence", "duration_ms"):
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            return None
        try:
            if not math.isfinite(number):
                return None
        except OverflowError:
            return None
    if not 0 <= value["confidence"] <= 1 or value["duration_ms"] < 0:
        return None
    if not isinstance(value.get("stable"), bool) or not isinstance(value.get("truncated"), bool):
        return None
    return {key: value[key] for key in ("choice", "confidence", "duration_ms", "stable", "truncated")}


def retrieve(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    root = root.resolve()
    config = json.loads((root / ".reflex_case.json").read_text())
    arm = config["arm"]
    if arm not in ARMS:
        raise ValueError("unsupported prepared arm")
    target = root / config["source_file"]
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError("source target escaped its prepared case")
    source_sha = sha(target)
    if source_sha != config["mutated_source_sha256"]:
        raise ValueError("retrieval must run on the exact prepared mutant before editing")
    request = json.loads((root / "request.json").read_text())
    if request != config["request"] or request.get("spec") != "context-route-v1":
        raise ValueError("prepared task request changed")
    runtime = root / ".reflex_runtime"
    require_clean_runtime(runtime)
    sys.path.insert(0, str(runtime))
    from reflexfoundry.context_benchmark import REPOSITORIES, _corpus, symbol_lookup, text_search
    from reflexfoundry.core import decision_contract_digest, digest, validate_inputs
    from reflexfoundry.model import LocalPolicy, artifact_digest

    inputs = validate_inputs(request["spec"], request["inputs"])
    repo = next(repo for repo in REPOSITORIES if repo.name == config["repository_name"])
    if repo.commit != config["commit"]:
        raise ValueError("source revision differs from fixed retrieval catalog")
    advisory: dict[str, Any] | None = None
    raw_prediction: dict[str, Any] | None = None
    call_ms, cli_code = 0.0, None
    model_path: Path | None = None
    policy_sha = report_sha = None
    inferred = False
    choice = "search"
    if arm == "deterministic-heuristic":
        choice = "symbol" if inputs.get("symbol", "").strip() else "search"
    elif arm == "ordinary-laya":
        model_path = Path(config["base_model"])
        call_started = time.perf_counter()
        # This is the unadapted public local model, not a hosted request.
        runtime_model = LocalPolicy(model_path, backend="torch")
        raw_prediction = prediction(runtime_model.predict(request["spec"], inputs))
        inferred = raw_prediction is not None
        call_ms = (time.perf_counter() - call_started) * 1000
        if raw_prediction is not None:
            choice = raw_prediction["choice"]
    elif arm in {"trained-always", "selective-shadow"}:
        policy_file, report_file = root / ".reflex/policy.json", root / ".reflex/report.json"
        policy = json.loads(policy_file.read_text())
        model_path = Path(policy["model"])
        policy_sha, report_sha = sha(policy_file), sha(report_file)
        env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR", "SYSTEMROOT") if key in os.environ}
        env.update(PYTHONPATH=str(runtime), PYTHONDONTWRITEBYTECODE="1",
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        call_started = time.perf_counter()
        try:
            result = subprocess.run(
                [sys.executable, "-B", str(runtime / "reflex_cli.py"), "decide", "request.json",
                 "--workspace", ".reflex", "--backend", "torch"],
                cwd=root, env=env, capture_output=True, text=True, timeout=120, check=False,
            )
            cli_code = result.returncode
            if cli_code == 0:
                value = json.loads(result.stdout)
                if isinstance(value, dict):
                    advisory = value
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            advisory = None
        call_ms = (time.perf_counter() - call_started) * 1000
        if advisory is None:
            advisory = {"choice": "search", "fallback": True, "mode": "shadow",
                        "reason": "local CLI did not return a valid advisory"}
        raw_prediction = prediction(advisory.get("prediction"))
        inferred = bool(raw_prediction is not None and advisory.get("mode") == "shadow"
                        and advisory.get("reason") == "shadow observation")
        if arm == "trained-always":
            # Offline read-only counterfactual on a public copy. Never deploy,
            # change a guard, or let this choice approve another action.
            choice = raw_prediction["choice"] if inferred and raw_prediction is not None else "search"
        else:
            choice = advisory.get("choice", "search")
        save(root / "advisory.json", advisory)
    if choice not in {"symbol", "search"}:
        raise ValueError("retrieval choice is outside the fixed catalog")
    corpus_started = time.perf_counter()
    corpus = _corpus(repo, root)
    corpus_ms = (time.perf_counter() - corpus_started) * 1000
    action_started = time.perf_counter()
    snippets = (symbol_lookup if choice == "symbol" else text_search)(corpus, inputs)
    action_ms = (time.perf_counter() - action_started) * 1000
    identity_started = time.perf_counter()
    model_digest = artifact_digest(model_path) if model_path is not None else None
    runtime_digest = digest(runtime_inventory(runtime))
    contract = decision_contract_digest()
    if sha(target) != source_sha:
        raise ValueError("source changed during the initial retrieval step")
    identity_ms = (time.perf_counter() - identity_started) * 1000
    value = {"arm": arm, "request": request, "choice": choice, "source_sha256": source_sha,
             "inference_observed": inferred, "policy_cli_exit_code": cli_code,
             "policy_call_ms": call_ms, "corpus_ms": corpus_ms, "retrieval_ms": action_ms,
             "identity_audit_ms": identity_ms, "step_wall_ms": (time.perf_counter() - started) * 1000,
             "snippets": snippets, "advisory": advisory, "prediction": raw_prediction,
             "scope": "Initial read-only retrieval; full repair validation remains mandatory. No policy deployment."}
    save(root / "context-result.json", value)
    return {"format": 1, "arm": arm, "request_digest": digest(request), "source_sha256": source_sha,
            "runtime_digest": runtime_digest, "cli_sha256": sha(runtime / "reflex_cli.py"),
            "model_artifact_digest": model_digest, "policy_sha256": policy_sha, "report_sha256": report_sha,
            "decision_contract_digest": contract, "inference_observed": inferred, "prediction": raw_prediction,
            "prediction_digest": digest(raw_prediction) if raw_prediction is not None else None,
            "choice": choice, "context_digest": digest(value),
            "step_wall_ms": value["step_wall_ms"], "policy_call_ms": call_ms,
            "identity_audit_ms": identity_ms}


def main() -> None:
    receipt = retrieve(Path.cwd())
    print(json.dumps({RECEIPT_KEY: receipt}, separators=(",", ":"), allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
