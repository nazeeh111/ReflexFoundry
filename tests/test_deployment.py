"""Deployment authority is bounded and depends on current, observed evidence."""

from dataclasses import replace

import pytest

from reflexfoundry import lifecycle
from reflexfoundry.core import SPECS, digest, read_json, write_json
from reflexfoundry.model import file_hash

INPUTS = {"summary": "Change calculation local validation behavior", "changed_files": ["calc.py"]}


class WarmPolicy:
    startup_ms = 0.0
    prediction = {
        "choice": "focused",
        "confidence": 0.99,
        "stable": True,
        "truncated": False,
        "duration_ms": 1.0,
    }
    seen = None

    def __init__(self, *_):
        pass

    def predict(self, spec, inputs):
        WarmPolicy.seen = inputs
        return dict(self.prediction)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"fake weights; no model executed")
    (model / "rl_agent_config.json").write_text("{}")
    for name in ("encoder", "tokenizer"):
        (model / name).mkdir()
        (model / name / "config.json").write_text("{}")
    rows = [{"inputs": INPUTS, "split": "train", "spec": "test-scope-v1"}]
    report = {
        "spec": "test-scope-v1",
        "model_digest": file_hash(model / "model.safetensors"),
        "dataset_digest": digest(rows),
        "calibration": {"threshold": 0.8},
        "deployment_allowed": True,
        "reasons": [],
    }
    write_json(model / "manifest.json", {"train_digest": digest(rows), "weights_sha256": report["model_digest"]})
    root = tmp_path / "workspace"
    lifecycle.register(root, model, report, rows)
    lifecycle.transition(root, "shadow")
    monkeypatch.setattr(lifecycle, "LocalPolicy", WarmPolicy)
    monkeypatch.setattr(WarmPolicy, "prediction", dict(WarmPolicy.prediction))
    return root, model, report, rows


def audited_shadow(root, n=30):
    for _ in range(n):
        request = lifecycle.decide(root, "test-scope-v1", INPUTS)
        assert request["choice"] == "full"
        assert request["candidate"] == "focused"
        lifecycle.outcome(root, request["request_id"], True, 10.0, candidate_verified=True)


def test_opt_in_requires_eligible_evaluation_and_real_unique_shadow_outcomes(environment):
    root, _, _, _ = environment
    with pytest.raises(ValueError, match="opt-in"):
        lifecycle.transition(root, "deploy")
    with pytest.raises(ValueError, match="30 verified"):
        lifecycle.transition(root, "deploy", opt_in=True)
    audited_shadow(root, 29)
    with pytest.raises(ValueError, match="30 verified"):
        lifecycle.transition(root, "deploy", opt_in=True)
    audited_shadow(root, 1)
    lifecycle.transition(root, "deploy", opt_in=True)
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["choice"] == "focused"
    # A different shadow epoch cannot reuse past observations.
    lifecycle.transition(root, "shadow")
    with pytest.raises(ValueError, match="30 verified"):
        lifecycle.transition(root, "deploy", opt_in=True)


def test_rejected_evaluation_cannot_be_deployed(environment):
    root, model, report, rows = environment
    report["deployment_allowed"] = False
    lifecycle.register(root, model, report, rows)
    lifecycle.transition(root, "shadow")
    audited_shadow(root)
    with pytest.raises(ValueError, match="blocked by evaluation"):
        lifecycle.transition(root, "deploy", opt_in=True)


def test_bounded_deployment_exhausts_without_an_extra_learned_decision(environment):
    root, _, _, _ = environment
    audited_shadow(root)
    lifecycle.transition(root, "deploy", opt_in=True, max_decisions=1)
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["choice"] == "focused"
    result = lifecycle.decide(root, "test-scope-v1", INPUTS)
    assert result["choice"] == "full"
    assert result["reason"] == "bounded deployment exhausted"
    assert read_json(root / "deployment.json")["mode"] == "off"


@pytest.mark.parametrize(
    "target", ["model.safetensors", "tokenizer/config.json", "encoder/config.json", "rl_agent_config.json"]
)
def test_changed_inference_bytes_revert(environment, target):
    root, model, _, _ = environment
    (model / target).write_text("changed")
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["choice"] == "full"
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_changed_candidate_catalog_reverts(environment, monkeypatch):
    root, _, _, _ = environment
    monkeypatch.setitem(SPECS, "test-scope-v1", replace(SPECS["test-scope-v1"], purpose="changed catalog"))
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["fallback"]
    assert read_json(root / "deployment.json")["mode"] == "off"


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", float("nan")),
        ("confidence", float("inf")),
        ("confidence", True),
        ("confidence", 1.1),
        ("duration_ms", -1),
        ("duration_ms", float("nan")),
        ("stable", "yes"),
        ("choice", "approve-permission"),
    ],
)
def test_malformed_prediction_never_reaches_agent(environment, monkeypatch, field, value):
    root, _, _, _ = environment
    monkeypatch.setitem(WarmPolicy.prediction, field, value)
    result = lifecycle.decide(root, "test-scope-v1", INPUTS)
    assert result["choice"] == "full"
    assert "prediction" not in result
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_uncertain_and_cold_predictions_abstain(environment, monkeypatch):
    root, _, _, _ = environment
    monkeypatch.setitem(WarmPolicy.prediction, "confidence", 0.5)
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["abstained"]
    monkeypatch.setitem(WarmPolicy.prediction, "confidence", 0.99)
    monkeypatch.setattr(WarmPolicy, "startup_ms", 1000.0)
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["abstained"]


def test_outcome_failure_reverts_and_cannot_be_replayed(environment):
    root, _, _, _ = environment
    request = lifecycle.decide(root, "test-scope-v1", INPUTS)
    outcome = lifecycle.outcome(root, request["request_id"], False, 10.0)
    assert outcome["deployment"]["mode"] == "off"
    assert outcome["deployment"]["history"][-1]["reason"] == "verified outcome regression"
    with pytest.raises(ValueError, match="already recorded"):
        lifecycle.outcome(root, request["request_id"], True, 10.0, candidate_verified=True)
    with pytest.raises(ValueError, match="unknown request"):
        lifecycle.outcome(root, "fabricated-request", True, 10.0)
    with pytest.raises(ValueError, match="finite"):
        lifecycle.outcome(root, request["request_id"], True, True)


def test_drift_reverts_and_no_private_inputs_are_persisted(environment, monkeypatch):
    root, _, _, _ = environment
    monkeypatch.setattr(lifecycle, "outside_domain", lambda *_: False)
    inputs = {
        "summary": "Change calculation local validation behavior api_key=privatevalue hello@example.com"
    }
    lifecycle.decide(root, "test-scope-v1", inputs)
    assert "privatevalue" not in str(WarmPolicy.seen)
    assert "hello@example.com" not in str(WarmPolicy.seen)
    assert "privatevalue" not in (root / "requests.json").read_text()
    monkeypatch.setattr(lifecycle, "outside_domain", lambda *_: True)
    result = lifecycle.decide(root, "test-scope-v1", INPUTS)
    assert result["reason"] == "input distribution drift"
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_re_registration_cannot_inherit_deployment_authority(environment):
    root, model, report, rows = environment
    audited_shadow(root)
    lifecycle.transition(root, "deploy", opt_in=True)
    lifecycle.register(root, model, report, rows)
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_changed_evaluation_report_reverts(environment):
    root, _, _, _ = environment
    policy = read_json(root / "policy.json")
    policy["report"]["calibration"]["threshold"] = 0.0
    write_json(root / "policy.json", policy)
    assert lifecycle.decide(root, "test-scope-v1", INPUTS)["fallback"]
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_evaluated_tokenizer_cannot_change_before_registration(environment):
    root, model, report, rows = environment
    report["artifact_digest"] = lifecycle.artifact_digest(model)
    (model / "tokenizer/config.json").write_text("changed")
    with pytest.raises(ValueError, match="evaluated inference artifacts"):
        lifecycle.register(root, model, report, rows)


@pytest.mark.parametrize("limit", [0, -1, 10001, True, 1.5])
def test_invalid_decision_limit_is_rejected(environment, limit):
    root, _, _, _ = environment
    with pytest.raises(ValueError, match="max_decisions"):
        lifecycle.transition(root, "shadow", max_decisions=limit)


def test_sustained_uncertainty_rolls_back(environment, monkeypatch):
    root, _, _, _ = environment
    monkeypatch.setitem(WarmPolicy.prediction, "confidence", 0.1)
    for _ in range(20):
        result = lifecycle.decide(root, "test-scope-v1", INPUTS)
    assert result["choice"] == "full"
    assert result["reason"] == "sustained abstention indicates uncertainty or drift"
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_parallel_requests_cannot_exceed_deployment_budget(environment):
    from concurrent.futures import ThreadPoolExecutor

    root, _, _, _ = environment
    audited_shadow(root)
    lifecycle.transition(root, "deploy", opt_in=True, max_decisions=3)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: lifecycle.decide(root, "test-scope-v1", INPUTS), range(6)))
    assert sum(r["choice"] == "focused" for r in results) == 3
    assert read_json(root / "deployment.json")["mode"] == "off"


def test_backend_exception_text_is_not_persisted(environment, monkeypatch):
    root, _, _, _ = environment

    class BrokenPolicy:
        def __init__(self, *_):
            raise RuntimeError("sensitive-input-must-not-leak")

    monkeypatch.setattr(lifecycle, "LocalPolicy", BrokenPolicy)
    result = lifecycle.decide(root, "test-scope-v1", INPUTS)
    assert result["choice"] == "full"
    assert "sensitive-input-must-not-leak" not in (root / "requests.json").read_text()
    assert read_json(root / "deployment.json")["mode"] == "off"
