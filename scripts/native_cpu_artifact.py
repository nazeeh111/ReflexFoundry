"""Create an explicit CPU-compatible copy; preserve the trained export verbatim.

Laya 0.4.16 normalizes TokenizersBackend metadata on first Torch load. Do that
known conversion before freezing a new version, then evaluate the new version.
This neither changes weights nor grants a policy deployment eligibility.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reflexfoundry.model import artifact_digest, file_hash  # noqa: E402


def prepare(source: Path, output: Path, source_release: str) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise FileExistsError("CPU compatibility output must be a fresh version")
    manifest = json.loads((source / "manifest.json").read_text())
    original_digest = artifact_digest(source)
    if (original_digest != manifest.get("inference_artifact_digest")
            or file_hash(source / "model.safetensors") != manifest.get("weights_sha256")):
        raise ValueError("source must match its original complete training identity")
    relative = Path("tokenizer/tokenizer_config.json")
    config = json.loads((source / relative).read_text())
    if config.get("tokenizer_class") != "TokenizersBackend" or isinstance(config.get("extra_special_tokens"), list):
        raise ValueError("only the declared TokenizersBackend compatibility conversion is supported")
    config["tokenizer_class"] = "PreTrainedTokenizerFast"
    config.pop("backend", None)
    config.pop("is_local", None)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reflex-cpu-compat-", dir=output.parent) as temp:
        stage = Path(temp) / "model"
        stage.mkdir()
        for name in ("model.safetensors", "rl_agent_config.json", "manifest.json"):
            shutil.copy2(source / name, stage / name)
        for name in ("encoder", "tokenizer"):
            shutil.copytree(source / name, stage / name)
        shutil.copy2(source / "manifest.json", stage / "training-manifest.original.json")
        # Match upstream's explicit JSON conversion, including its lack of a
        # trailing newline. No other tokenizer or inference bytes change.
        (stage / relative).write_text(json.dumps(config, indent=2))
        record = {"operation": "explicit upstream CPU tokenizer-class compatibility normalization before artifact freeze",
            "source_release": source_release, "source_inference_digest": original_digest,
            "source_manifest_sha256": file_hash(source / "manifest.json"),
            "normalized_inference_digest": artifact_digest(stage), "changed_file": str(relative),
            "before_sha256": file_hash(source / relative), "after_sha256": file_hash(stage / relative),
            "weight_bytes_unchanged": file_hash(stage / "model.safetensors") == manifest["weights_sha256"],
            "tokenizer_json_bytes_unchanged": file_hash(stage / "tokenizer/tokenizer.json") == file_hash(source / "tokenizer/tokenizer.json"),
            "backend": "laya0.4.16 torch"}
        if (artifact_digest(source) != original_digest or not record["weight_bytes_unchanged"]
                or not record["tokenizer_json_bytes_unchanged"]):
            raise ValueError("source or copied inference bytes changed during compatibility conversion")
        manifest["compatibility_derivation"] = record
        manifest["inference_artifact_digest"] = record["normalized_inference_digest"]
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if output.exists() or output.is_symlink():
            raise FileExistsError("CPU compatibility output already exists")
        stage.rename(output)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-release", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.source_release), indent=2))
