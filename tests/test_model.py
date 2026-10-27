"""Validate the real policy adapter boundary without downloading a model."""
import copy
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from reflexfoundry.model import BASE_REVISION, LocalPolicy, artifact_digest, file_hash, materialize


def policy(first=.99, second=.98, probabilities=None):
    answers = iter([
        {"answers": {"decision": {"choice": "focused", "answer_confidence": confidence,
            "probabilities": copy.deepcopy(probabilities or {"focused": .99, "full": .01})}},
         "usage": {"truncated": False}}
        for confidence in (first, second)
    ])
    runtime = LocalPolicy.__new__(LocalPolicy)
    runtime.agent = SimpleNamespace(predict=lambda *_args, **_kwargs: next(answers))
    runtime.backend = "test-only"
    return runtime


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -.1, 1.1, True, ".99", None, 10**400])
@pytest.mark.parametrize("position", ["first", "second"])
def test_each_order_pass_requires_real_finite_confidence(value, position):
    with pytest.raises(ValueError, match="confidence"):
        policy(**{position: value}).predict("test-scope-v1", {"summary": "Fix display"})


@pytest.mark.parametrize("probabilities", [
    {"focused": float("nan"), "full": .01}, {"focused": True, "full": 0},
    {"focused": ".99", "full": .01}, {"focused": .99, "full": .99},
    {"approve": 1.0, "full": 0}, {"focused": .99},
])
def test_invalid_candidate_distributions_are_rejected(probabilities):
    with pytest.raises(ValueError, match="probabilities"):
        policy(probabilities=probabilities).predict("test-scope-v1", {"summary": "Fix display"})


def test_both_valid_passes_preserve_conservative_confidence():
    result = policy(first=.99, second=.8).predict("test-scope-v1", {"summary": "Fix display"})
    assert result["confidence"] == .8
    assert result["stable"] is True


def test_missing_truncation_evidence_abstains_and_malformed_responses_reject():
    result = {"answers": {"decision": {"choice": "focused", "probabilities": {"focused": .99, "full": .01}}}}
    runtime = policy()
    runtime.agent = SimpleNamespace(predict=lambda *_args, **_kwargs: result)
    assert runtime.predict("test-scope-v1", {"summary": "Fix display"})["truncated"] is True
    runtime.agent = SimpleNamespace(predict=lambda *_args, **_kwargs: {"answers": {"decision": []}})
    with pytest.raises(ValueError, match="decision response"):
        runtime.predict("test-scope-v1", {"summary": "Fix display"})


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    # Test-only serialization stub exercises filesystem integrity and atomic
    # publication in core-only CI. No tensor inference or scientific result.
    base, package, expected = [tmp_path / name for name in ("base", "adapter", "expected")]
    for root in (base, package, expected):
        root.mkdir()
    (base / "model.safetensors").write_bytes(b"base")
    (package / "head.safetensors").write_bytes(b"head")
    for root in (package, expected):
        (root / "rl_agent_config.json").write_text('{"temperature": 2}')
        for name in ("encoder", "tokenizer"):
            (root / name).mkdir()
            (root / name / "config.json").write_text('{"format": "test-only"}')
    (expected / "model.safetensors").write_bytes(b"reconstructed")
    manifest = {"base_revision": BASE_REVISION, "head_sha256": file_hash(package / "head.safetensors"),
                "base_weights_sha256": file_hash(base / "model.safetensors"),
                "weights_sha256": file_hash(expected / "model.safetensors"),
                "inference_artifact_digest": artifact_digest(expected)}
    (package / "manifest.json").write_text(json.dumps(manifest))
    tensors = {"encoder.value": SimpleNamespace(shape=(1,)), "head.value": SimpleNamespace(shape=(1,))}
    safetensors = ModuleType("safetensors")
    backend = ModuleType("safetensors.torch")
    def load_file(path):
        return {k: v for k, v in tensors.items() if "head.safetensors" not in path or k.startswith("head.")}
    def save_file(state, path):
        from pathlib import Path
        assert set(state) == set(tensors)
        Path(path).write_bytes(b"reconstructed")
    backend.load_file = load_file
    backend.save_file = save_file
    monkeypatch.setitem(sys.modules, "safetensors", safetensors)
    monkeypatch.setitem(sys.modules, "safetensors.torch", backend)
    return base, package, expected


def test_materialize_checks_entire_inference_artifact(adapter, tmp_path):
    base, package, expected = adapter
    output = tmp_path / "result"
    materialize(base, package / "head.safetensors", output)
    assert artifact_digest(output) == artifact_digest(expected)
    assert (output / "manifest.json").read_bytes() == (package / "manifest.json").read_bytes()


@pytest.mark.parametrize("name", ["rl_agent_config.json", "tokenizer/config.json", "encoder/config.json"])
def test_changed_metadata_cannot_publish_a_partial_policy(adapter, tmp_path, name):
    base, package, _ = adapter
    (package / name).write_text('{"format": "changed"}')
    output = tmp_path / "result"
    with pytest.raises(ValueError, match="inference artifacts"):
        materialize(base, package / "head.safetensors", output)
    assert not output.exists()
    assert not list(tmp_path.glob(".reflex-materialize-*"))


def test_materialize_refuses_unbound_or_existing_output(adapter, tmp_path):
    base, package, _ = adapter
    output = tmp_path / "result"
    output.mkdir()
    (output / "original").write_text("preserve me")
    with pytest.raises(ValueError, match="already exists"):
        materialize(base, package / "head.safetensors", output)
    assert (output / "original").read_text() == "preserve me"
    manifest = json.loads((package / "manifest.json").read_text())
    del manifest["inference_artifact_digest"]
    (package / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="complete inference"):
        materialize(base, package / "head.safetensors", tmp_path / "fresh")
