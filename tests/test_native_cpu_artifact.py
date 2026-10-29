import importlib.util
import json
from pathlib import Path

import pytest

from reflexfoundry.model import artifact_digest, file_hash

spec = importlib.util.spec_from_file_location("native_cpu_artifact", Path(__file__).resolve().parents[1] / "scripts/native_cpu_artifact.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_explicit_conversion_preserves_original_and_records_derivation(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    (source / "model.safetensors").write_bytes(b"test-only weights, no inference")
    (source / "rl_agent_config.json").write_text("{}")
    for name in ("encoder", "tokenizer"):
        (source / name).mkdir()
    (source / "encoder/config.json").write_text("{}")
    (source / "tokenizer/tokenizer.json").write_text('{"test-only": true}')
    (source / "tokenizer/tokenizer_config.json").write_text(json.dumps({
        "tokenizer_class": "TokenizersBackend", "backend": "tokenizers", "is_local": True, "pad_token": "[PAD]"}))
    original = artifact_digest(source)
    manifest = {"weights_sha256": file_hash(source / "model.safetensors"), "inference_artifact_digest": original}
    (source / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "derived"
    record = module.prepare(source, output, "test-only source version")
    assert artifact_digest(source) == original
    assert record["normalized_inference_digest"] == artifact_digest(output) != original
    assert record["weight_bytes_unchanged"] and record["tokenizer_json_bytes_unchanged"]
    assert (output / "training-manifest.original.json").read_bytes() == (source / "manifest.json").read_bytes()
    config = json.loads((output / "tokenizer/tokenizer_config.json").read_text())
    assert config == {"tokenizer_class": "PreTrainedTokenizerFast", "pad_token": "[PAD]"}
    with pytest.raises(FileExistsError):
        module.prepare(source, output, "test-only source version")
    (source / "encoder/config.json").write_text('{"changed": true}')
    with pytest.raises(ValueError, match="original complete"):
        module.prepare(source, tmp_path / "bad", "test-only")
    assert not (tmp_path / "bad").exists()
