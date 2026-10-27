"""Local Laya adaptation with pinned weights and a portable PyTorch fallback."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from pathlib import Path
from typing import Any

from .core import SPECS, digest, validate_inputs, validate_splits, write_json

BASE_MODEL = "convaiinnovations/laya"
BASE_REVISION = "7b928d828b7b0e022f929d9bd2e44165aa270148"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(destination: Path) -> Path:
    from huggingface_hub import snapshot_download
    snapshot_download(BASE_MODEL, revision=BASE_REVISION, local_dir=str(destination),
                      allow_patterns=["model.safetensors", "rl_agent_config.json", "encoder/*",
                                      "tokenizer/*", "README.md"])
    return destination


def train(records: list[dict[str, Any]], base: Path, output: Path,
          epochs: int = 4, device: str = "auto") -> dict[str, Any]:
    from laya.train import TrainConfig, finetune
    validate_splits(records)
    if output.exists():
        raise ValueError("training output exists; choose a fresh version directory")
    rows = [r for r in records if r["split"] == "train"]
    if len(rows) < 20:
        raise ValueError("at least 20 training decisions required")
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = output.parent / (output.name + "-train.jsonl")
    with dataset.open("w") as handle:
        for row in rows:
            spec = SPECS[row["spec"]]
            handle.write(json.dumps({"state": row["inputs"],
                "questions": {"decision": spec.question()},
                "expected": {"decision": row["selected"]}}) + "\n")
    start = time.perf_counter()
    # Only train split reaches the upstream trainer. Its internal calibration is train-only;
    # external calibration below determines delegation, separate from promotion and test.
    if isinstance(epochs, bool) or not isinstance(epochs, int) or not 1 <= epochs <= 100:
        raise ValueError("epochs must be an integer from 1 to 100")
    config = TrainConfig(epochs=epochs, micro_batch=4, grad_accum=1,
        freeze_encoder=True, loss="soft-ce", head_lr=1e-4, max_len=256,
        shuffle_options=("choice",), calib_frac=0.15, seed=17, log_every=20)
    summary = finetune(str(dataset), str(base), str(output), config, device=device)
    elapsed = (time.perf_counter() - start) * 1000
    from safetensors.torch import load_file, save_file
    state = load_file(str(output / "model.safetensors"))
    head = {k: v for k, v in state.items() if not k.startswith("encoder.")}
    save_file(head, str(output / "head.safetensors"))
    manifest = {"format": 1, "base_model": BASE_MODEL, "base_revision": BASE_REVISION, "base_weights_sha256": file_hash(base / "model.safetensors"),
        "backend": "laya-native-frozen-encoder", "training_ms": elapsed,
        "training_records": len(rows), "train_digest": digest(rows),
        "spec_catalog_digest": digest([s.__dict__ for s in SPECS.values()]),
        "head_sha256": file_hash(output / "head.safetensors"),
        "weights_sha256": file_hash(output / "model.safetensors"), "summary": summary}
    write_json(output / "manifest.json", manifest)
    return manifest


class LocalPolicy:
    def __init__(self, path: Path, backend: str = "auto"):
        start = time.perf_counter()
        if backend == "auto":
            backend = "mlx" if platform.system() == "Darwin" and platform.machine() == "arm64" else "torch"
        if backend == "mlx":
            import laya_mlx as runtime
            self.agent = runtime.load(str(path))
        elif backend == "torch":
            import laya as runtime
            self.agent = runtime.load(str(path), device="cpu")
        else:
            raise ValueError("backend must be auto, mlx or torch")
        self.backend = backend
        self.startup_ms = (time.perf_counter() - start) * 1000
        self.path = path

    def predict(self, spec_id: str, inputs: dict[str, Any], check_order: bool = True) -> dict[str, Any]:
        validate_inputs(spec_id, inputs)
        spec = SPECS[spec_id]
        start = time.perf_counter()
        first = self.agent.predict(inputs, {"decision": spec.question()}, max_len=256)
        answer = first["answers"]["decision"]
        # Candidate-order instability always abstains. Both passes are charged.
        second = self.agent.predict(inputs, {"decision": spec.question(reverse=True)}, max_len=256) if check_order else first
        other = second["answers"]["decision"]
        elapsed = (time.perf_counter() - start) * 1000
        choice = answer["choice"]
        confidence = min(float(a.get("answer_confidence", max(a["probabilities"].values())))
                         for a in (answer, other))
        if choice not in spec.choices or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("model returned invalid choice or confidence")
        stable = choice == other["choice"]
        usage = first.get("usage", {})
        truncated = bool(usage.get("truncated") or second.get("usage", {}).get("truncated"))
        return {"choice": choice, "confidence": confidence, "stable": stable,
            "truncated": truncated, "duration_ms": elapsed, "probabilities": answer["probabilities"],
            "backend": self.backend}


def materialize(base: Path, head: Path, output: Path) -> None:
    """Reconstruct an adapter using only safetensors, never executable pickle weights."""
    import shutil

    from safetensors.torch import load_file, save_file
    if output.exists():
        raise ValueError("materialization output already exists")
    manifest = json.loads((head.parent / "manifest.json").read_text())
    if manifest["base_revision"] != BASE_REVISION or file_hash(head) != manifest["head_sha256"]:
        raise ValueError("adapter provenance or head digest mismatch")
    if file_hash(base / "model.safetensors") != manifest["base_weights_sha256"]:
        raise ValueError("base checkpoint does not match adapter provenance")
    state = load_file(str(base / "model.safetensors"))
    adapted = load_file(str(head))
    expected = {k for k in state if not k.startswith("encoder.")}
    if set(adapted) != expected or any(adapted[k].shape != state[k].shape for k in expected):
        raise ValueError("head keys or shapes do not match the pinned base")
    state.update(adapted)
    output.mkdir(parents=True)
    for name in ("encoder", "tokenizer"):
        shutil.copytree(head.parent / name, output / name)
    shutil.copy2(head.parent / "rl_agent_config.json", output / "rl_agent_config.json")
    shutil.copy2(head.parent / "manifest.json", output / "manifest.json")
    save_file(state, str(output / "model.safetensors"))
