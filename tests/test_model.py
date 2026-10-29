"""Validate the real policy adapter boundary without downloading a model."""
import copy
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from reflexfoundry.model import (
    BASE_REVISION,
    LocalPolicy,
    artifact_digest,
    file_hash,
    materialize,
    training_examples,
)


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


def test_training_uses_verified_outcomes_and_excludes_unusable_labels():
    base = {"id": "safe", "spec": "context-route-v1", "inputs": {"summary": "Find source"},
            "selected": "symbol", "outcomes": {"symbol": {"success": False, "duration_ms": 1},
                                               "search": {"success": True, "duration_ms": 10}}}
    neither = base | {"id": "neither", "outcomes": {
        "symbol": {"success": False, "duration_ms": 1}, "search": {"success": False, "duration_ms": 2}}}
    observed = {key: value for key, value in base.items() if key != "outcomes"} | {"id": "observed"}
    examples, supervision = training_examples([base, neither, observed])
    assert [item["expected"]["decision"] for item in examples] == ["search", "symbol"]
    assert supervision["label_sources"] == {"independent-outcome": 1, "observed-choice": 1}
    assert supervision["excluded_no_success"] == ["neither"]


def test_training_prefers_original_workflow_on_near_ties():
    examples, _ = training_examples([{"id": "tie", "spec": "context-route-v1",
        "inputs": {"summary": "Find source"}, "selected": "symbol",
        "outcomes": {"symbol": {"success": True, "duration_ms": 10},
                     "search": {"success": True, "duration_ms": 10.2}}}])
    assert examples[0]["expected"]["decision"] == "search"


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


@pytest.mark.parametrize('config', [
    {'tokenizer_class': 'TokenizersBackend', 'backend': 'tokenizers', 'is_local': True, 'pad_token': '[PAD]'},
    {'pad_token': '[PAD]'},
    {'tokenizer_class': 'PreTrainedTokenizerFast', 'extra_special_tokens': ['<A>', '<B>']},
])
def test_new_export_is_loader_compatible_before_binding_and_keeps_original(tmp_path, config):
    from reflexfoundry.model import _finalize_tokenizer_export
    (tmp_path / 'tokenizer').mkdir()
    path = tmp_path / 'tokenizer/tokenizer_config.json'
    path.write_text(json.dumps(config))
    original = path.read_bytes()
    (tmp_path / 'tokenizer/tokenizer.json').write_bytes(b'unchanged actual tokenizer')
    (tmp_path / 'model.safetensors').write_bytes(b'unchanged weights')
    result = _finalize_tokenizer_export(tmp_path)
    assert result is not None
    normalized = json.loads(path.read_text())
    assert normalized['tokenizer_class'] == 'PreTrainedTokenizerFast'
    assert normalized.get('extra_special_tokens') is None or isinstance(normalized['extra_special_tokens'], dict)
    assert (tmp_path / 'tokenizer-export.original.json').read_bytes() == original
    assert result['after_sha256'] == file_hash(path)
    assert (tmp_path / 'tokenizer/tokenizer.json').read_bytes() == b'unchanged actual tokenizer'
    assert (tmp_path / 'model.safetensors').read_bytes() == b'unchanged weights'
    normalized_bytes = path.read_bytes()
    assert _finalize_tokenizer_export(tmp_path) is None  # A load needs no further rewrite.
    assert path.read_bytes() == normalized_bytes


def test_compatible_export_is_not_rewritten_and_conflicting_backup_is_preserved(tmp_path):
    from reflexfoundry.model import _finalize_tokenizer_export
    (tmp_path / 'tokenizer').mkdir()
    path = tmp_path / 'tokenizer/tokenizer_config.json'
    path.write_text('{"tokenizer_class": "PreTrainedTokenizerFast"}\n')
    original = path.read_bytes()
    assert _finalize_tokenizer_export(tmp_path) is None
    assert path.read_bytes() == original
    assert not (tmp_path / 'tokenizer-export.original.json').exists()
    path.write_text('{"tokenizer_class":"TokenizersBackend"}')
    before = path.read_bytes()
    backup = tmp_path / 'tokenizer-export.original.json'
    backup.write_bytes(b'preserve existing provenance')
    with pytest.raises(FileExistsError):
        _finalize_tokenizer_export(tmp_path)
    assert backup.read_bytes() == b'preserve existing provenance'
    assert path.read_bytes() == before


def test_materialize_preserves_and_validates_new_export_provenance(adapter, tmp_path):
    base, package, expected = adapter
    for root in (package, expected):
        (root / 'tokenizer/tokenizer_config.json').write_text('{"tokenizer_class":"PreTrainedTokenizerFast"}')
    original = package / 'tokenizer-export.original.json'
    original.write_text('{"tokenizer_class":"TokenizersBackend"}')
    manifest_path = package / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['inference_artifact_digest'] = artifact_digest(expected)
    manifest['tokenizer_export_compatibility'] = {
        'original_file': original.name, 'before_sha256': file_hash(original),
        'after_sha256': file_hash(package / 'tokenizer/tokenizer_config.json')}
    manifest_path.write_text(json.dumps(manifest))
    result = tmp_path / 'reconstructed-with-provenance'
    materialize(base, package / 'head.safetensors', result)
    assert (result / original.name).read_bytes() == original.read_bytes()
    original.write_bytes(b'changed provenance')
    with pytest.raises(ValueError, match='provenance'):
        materialize(base, package / 'head.safetensors', tmp_path / 'bad-provenance')
    assert not (tmp_path / 'bad-provenance').exists()


def test_export_normalization_refuses_a_linked_tokenizer_directory(tmp_path):
    from reflexfoundry.model import _finalize_tokenizer_export
    outside = tmp_path / 'original-tokenizer'
    outside.mkdir()
    config = outside / 'tokenizer_config.json'
    config.write_text('{"tokenizer_class":"TokenizersBackend"}')
    before = config.read_bytes()
    output = tmp_path / 'new-export'
    output.mkdir()
    (output / 'tokenizer').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='regular configuration'):
        _finalize_tokenizer_export(output)
    assert config.read_bytes() == before
    assert not (output / 'tokenizer-export.original.json').exists()


def test_train_freezes_the_normalized_export_not_the_loader_mutable_bytes(tmp_path, monkeypatch):
    from pathlib import Path

    import reflexfoundry.model as model
    # Serialization and trainer doubles exercise export ordering in core-only
    # CI. Actual model-loader verification is a separate recorded local check.
    trainer = ModuleType('laya.train')
    trainer.TrainConfig = lambda **kwargs: SimpleNamespace(**kwargs)
    def finetune(_dataset, _base, output, _config, **_kwargs):
        root = Path(output)
        (root / 'tokenizer').mkdir(parents=True)
        (root / 'encoder').mkdir()
        (root / 'tokenizer/tokenizer_config.json').write_text('{"tokenizer_class":"TokenizersBackend"}')
        (root / 'tokenizer/tokenizer.json').write_text('{}')
        (root / 'encoder/config.json').write_text('{}')
        (root / 'model.safetensors').write_bytes(b'new training export')
        (root / 'rl_agent_config.json').write_text('{}')
        return {'test_only': True}
    trainer.finetune = finetune
    monkeypatch.setitem(sys.modules, 'laya', ModuleType('laya'))
    monkeypatch.setitem(sys.modules, 'laya.train', trainer)
    tensors = ModuleType('safetensors.torch')
    tensors.load_file = lambda _path: {'encoder.example': None, 'head.example': None}
    tensors.save_file = lambda _state, path: Path(path).write_bytes(b'test-only head')
    monkeypatch.setitem(sys.modules, 'safetensors', ModuleType('safetensors'))
    monkeypatch.setitem(sys.modules, 'safetensors.torch', tensors)
    monkeypatch.setattr(model, 'validate_splits', lambda _records: None)
    base = tmp_path / 'base'
    base.mkdir()
    (base / 'model.safetensors').write_bytes(b'base')
    rows = [{'id': str(i), 'spec': 'context-route-v1', 'split': 'train',
             'inputs': {'summary': f'example{i}'}, 'selected': 'search'} for i in range(20)]
    output = tmp_path / 'trained'
    manifest = model.train(rows, base, output)
    assert manifest['inference_artifact_digest'] == artifact_digest(output)
    assert manifest['tokenizer_export_compatibility']['after_sha256'] == file_hash(output / 'tokenizer/tokenizer_config.json')
    assert json.loads((output / 'tokenizer/tokenizer_config.json').read_text())['tokenizer_class'] == 'PreTrainedTokenizerFast'
    assert (output / 'tokenizer-export.original.json').is_file()


@pytest.mark.parametrize('config', [
    {'tokenizer_class': 'TokenizersBackend'}, {},
    {'tokenizer_class': 'PreTrainedTokenizerFast', 'extra_special_tokens': ['<A>']},
])
def test_cpu_refuses_loader_mutation_before_import_or_access_to_model(tmp_path, monkeypatch, config):
    directory = tmp_path / 'tokenizer'
    directory.mkdir()
    path = directory / 'tokenizer_config.json'
    path.write_text(json.dumps(config))
    original = path.read_bytes()
    runtime = ModuleType('laya')
    runtime.load = lambda *_args, **_kwargs: pytest.fail('unsafe loader must not run')
    monkeypatch.setitem(sys.modules, 'laya', runtime)
    with pytest.raises(ValueError, match='explicit converted version'):
        LocalPolicy(tmp_path, 'torch')
    assert path.read_bytes() == original
    assert not (tmp_path / 'tokenizer-export.original.json').exists()


def test_cpu_loads_a_compatible_version_without_modifying_it(tmp_path, monkeypatch):
    directory = tmp_path / 'tokenizer'
    directory.mkdir()
    path = directory / 'tokenizer_config.json'
    path.write_text('{"tokenizer_class":"PreTrainedTokenizerFast"}')
    original = path.read_bytes()
    runtime = ModuleType('laya')
    loaded = []
    runtime.load = lambda *args, **kwargs: loaded.append((args, kwargs)) or SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'laya', runtime)
    LocalPolicy(tmp_path, 'torch')
    assert len(loaded) == 1
    assert path.read_bytes() == original
