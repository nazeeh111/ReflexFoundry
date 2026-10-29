"""Independent review boundaries; these tests specify required fail-closed behavior."""
from pathlib import Path

import pytest

from reflexfoundry.core import SPECS, decision_contract_digest, digest, write_json
from reflexfoundry.evaluation import evaluate, summarize
from reflexfoundry.lifecycle import artifact_digest, register, transition
from reflexfoundry.model import file_hash


def _model(root: Path) -> Path:
    model = root / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"test-only-weights")
    (model / "rl_agent_config.json").write_text("{}")
    for name in ("encoder", "tokenizer"):
        (model / name).mkdir()
        (model / name / "config.json").write_text("{}")
    return model


def test_baseline_shadow_success_cannot_verify_unexecuted_candidate(tmp_path):
    model = _model(tmp_path)
    report = {"deployment_allowed": True, "calibration": {"threshold": .9}, "reasons": []}
    policy = {"id": "p", "spec": "test-scope-v1", "model": str(model),
              "decision_contract_digest": decision_contract_digest(),
              "spec_digest": digest(SPECS["test-scope-v1"].__dict__),
              "artifact_digest": artifact_digest(model), "report": report,
              "report_digest": digest(report)}
    write_json(tmp_path / "policy.json", policy)
    state = transition(tmp_path, "shadow")
    # These reflect the API's shadow semantics: the actual executed choice is full.
    # No independent outcome for the proposed focused scope has been recorded.
    write_json(tmp_path / "requests.json", [
        {"request_id": str(i), "policy": "p", "report_digest": policy["report_digest"],
         "mode": "shadow", "choice": "full", "candidate": "focused", "fallback": True,
         "abstained": False, "deployment_epoch": state["epoch"],
         "success": True, "outcome_ms": 100}
        for i in range(30)
    ])
    with pytest.raises(ValueError):
        transition(tmp_path, "deploy", opt_in=True)


def _dataset():
    rows, predictions = [], {}
    for split in ("train", "calibration", "promotion", "test"):
        for i in range(60):
            key = f"{split}-{i}"
            rare = i == 0
            rows.append({"id": key, "repository": key, "split": split,
                         "spec": "test-scope-v1", "selected": "focused", "authorized": True,
                         "inputs": {"summary": "Fix " + key,
                                    "changed_files": ["labels.py" if rare else "units.py"]},
                         "outcomes": {"focused": {"success": True, "duration_ms": 10},
                                      "full": {"success": not rare, "duration_ms": 100}}})
            predictions[key] = {"choice": "full" if rare else "focused", "confidence": .99,
                                "stable": True, "truncated": False, "duration_ms": 1}
    return rows, predictions


def test_faster_policy_cannot_regress_success_against_heuristic():
    rows, predictions = _dataset()
    report = evaluate(rows, predictions, 0, "weights")
    policies = {p["name"]: p for p in report["promotion"]["policies"]}
    assert policies["deterministic-heuristic"]["success_rate"] > policies["selective"]["success_rate"]
    assert not report["deployment_allowed"]


def test_cold_start_budget_is_applied_to_evaluation_choices():
    rows, predictions = _dataset()
    rows = [r for r in rows if r["split"] == "promotion"]
    report = summarize(rows, predictions, .9, startup_ms=300)
    # Live decide charges startup on every request and must fall back above 250ms.
    assert report["accepted"] == 0
    selective = next(p for p in report["policies"] if p["name"] == "selective")
    assert selective["fallback_rate"] == 1


def test_registration_rejects_model_from_different_training_records(tmp_path):
    model = _model(tmp_path)
    records = [{"split": "train", "inputs": {"summary": "Train A"}}]
    write_json(model / "manifest.json", {"train_digest": digest(["different-data"]),
               "spec_catalog_digest": digest([s.__dict__ for s in SPECS.values()])})
    report = {"dataset_digest": digest(records), "spec": "test-scope-v1",
              "model_digest": file_hash(model / "model.safetensors"),
              "deployment_allowed": False, "calibration": {"threshold": 1.01}}
    with pytest.raises(ValueError, match="train"):
        register(tmp_path / "workspace", model, report, records)


def test_locked_test_cannot_regress_against_heuristic():
    rows, predictions = _dataset()
    # Promotion is strictly safe. Only the final test reveals the candidate's
    # quality loss against the deterministic heuristic; full has the same error.
    for row in rows:
        if row["split"] != "test":
            predictions[row["id"]]["choice"] = "focused"
    report = evaluate(rows, predictions, 0, "weights")
    policies = {p["name"]: p for p in report["test"]["policies"]}
    assert policies["deterministic-heuristic"]["success_rate"] > policies["selective"]["success_rate"]
    assert not report["deployment_allowed"]


def test_privacy_redaction_preserves_valid_json_at_home_path_end():
    from reflexfoundry.core import privacy_filter
    assert privacy_filter({"summary": "Inspect /Users/alice"}) == {"summary": "Inspect /[HOME]"}
