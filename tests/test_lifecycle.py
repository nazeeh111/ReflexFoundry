import pytest

from reflexfoundry.core import SPECS, digest, read_json, write_json
from reflexfoundry.lifecycle import decide, outcome, transition


def setup(root, eligible=False):
    policy = {"id": "p", "spec": "test-scope-v1", "spec_digest": digest(SPECS["test-scope-v1"].__dict__),
        "model": "/nonexistent", "model_digest": "hash", "vocabulary": ["fix", "display", "summary"],
        "report": {"deployment_allowed": eligible, "reasons": ["no improvement"],
                   "calibration": {"threshold": .9}}}
    policy["report_digest"] = digest(policy["report"])
    write_json(root / "policy.json", policy)


def test_no_deployment_without_evidence_optin_and_shadow(tmp_path, monkeypatch):
    setup(tmp_path)
    transition(tmp_path, "shadow")
    with pytest.raises(ValueError, match="opt-in"):
        transition(tmp_path, "deploy")
    with pytest.raises(ValueError, match="blocked"):
        transition(tmp_path, "deploy", True)
    setup(tmp_path, eligible=True)
    monkeypatch.setattr("reflexfoundry.lifecycle._binding_valid", lambda *_: True)
    with pytest.raises(ValueError, match="30 verified shadow"):
        transition(tmp_path, "deploy", True)


def test_model_unavailable_falls_back(tmp_path):
    setup(tmp_path)
    transition(tmp_path, "shadow")
    result = decide(tmp_path, "test-scope-v1", {"summary": "Fix display"})
    assert result["choice"] == "full" and result["fallback"]
    assert "unavailable" in result["reason"]


def test_outcome_regression_rolls_back_and_cannot_be_overwritten(tmp_path):
    setup(tmp_path)
    transition(tmp_path, "shadow")
    write_json(tmp_path / "requests.json", [{"request_id": "r", "policy": "p", "mode": "shadow"}])
    outcome(tmp_path, "r", False, 23)
    assert read_json(tmp_path / "deployment.json")["mode"] == "off"
    with pytest.raises(ValueError, match="already recorded"):
        outcome(tmp_path, "r", True, 20)


def test_unknown_domain_reverts_deployment(tmp_path):
    setup(tmp_path)
    write_json(tmp_path / "deployment.json", {"mode": "deployed", "policy": "p", "history": []})
    result = decide(tmp_path, "test-scope-v1", {"summary": "Quantum photonic compiler optimization"})
    assert result["fallback"]
    assert read_json(tmp_path / "deployment.json")["mode"] == "off"
