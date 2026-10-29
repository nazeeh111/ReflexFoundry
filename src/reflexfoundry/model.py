"""Local Laya adaptation with pinned weights and a portable PyTorch fallback."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .core import SPECS, digest, finite_number, validate_inputs, validate_splits, write_json

BASE_MODEL = "convaiinnovations/laya"
BASE_REVISION = "7b928d828b7b0e022f929d9bd2e44165aa270148"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def artifact_digest(model: Path) -> str:
    """Bind every inference input, including tokenizer and configuration bytes."""
    files = [model / "model.safetensors", model / "rl_agent_config.json"]
    for name in ("encoder", "tokenizer"):
        directory = model / name
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError("model needs real encoder and tokenizer directories")
        files.extend(p for p in directory.rglob("*") if p.is_file() or p.is_symlink())
    if any(not p.is_file() or p.is_symlink() for p in files):
        raise ValueError("inference artifacts must be regular files")
    return digest([(str(p.relative_to(model)), file_hash(p)) for p in sorted(files)])


def download(destination: Path) -> Path:
    from huggingface_hub import snapshot_download
    snapshot_download(BASE_MODEL, revision=BASE_REVISION, local_dir=str(destination),
                      allow_patterns=["model.safetensors", "rl_agent_config.json", "encoder/*",
                                      "tokenizer/*", "README.md"])
    return destination


def training_examples(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prefer independently measured successful actions over observed agreement."""
    examples = []
    sources: Counter[str] = Counter()
    excluded = []
    for row in rows:
        spec = SPECS[row["spec"]]
        outcomes = row.get("outcomes", {})
        label = row["selected"]
        if outcomes:
            safe = [choice for choice in spec.choices if outcomes[choice]["success"]]
            if not safe:
                excluded.append(row["id"])
                continue
            label = min(safe, key=lambda choice: outcomes[choice]["duration_ms"])
            if (spec.fallback in safe
                    and outcomes[spec.fallback]["duration_ms"] <= outcomes[label]["duration_ms"] * 1.03):
                label = spec.fallback
            sources["independent-outcome"] += 1
        else:
            sources["observed-choice"] += 1
        examples.append({"state": row["inputs"], "questions": {"decision": spec.question()},
                         "expected": {"decision": label}})
    return examples, {"label_sources": dict(sources), "excluded_no_success": excluded,
                      "examples_digest": digest(examples)}


def train(records: list[dict[str, Any]], base: Path, output: Path,
          epochs: int = 4, device: str = "auto") -> dict[str, Any]:
    from laya.train import TrainConfig, finetune
    validate_splits(records)
    if output.exists():
        raise ValueError("training output exists; choose a fresh version directory")
    rows = [r for r in records if r["split"] == "train"]
    examples, supervision = training_examples(rows)
    if len(examples) < 20:
        raise ValueError("at least 20 usable training decisions required; failed outcomes cannot be positive labels")
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = output.parent / (output.name + "-train.jsonl")
    with dataset.open("w") as handle:
        for example in examples:
            handle.write(json.dumps(example) + "\n")
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
        "training_records": len(examples), "training_records_available": len(rows),
        "supervision": supervision, "train_digest": digest(rows),
        "spec_catalog_digest": digest([s.__dict__ for s in SPECS.values()]),
        "head_sha256": file_hash(output / "head.safetensors"),
        "weights_sha256": file_hash(output / "model.safetensors"),
        "inference_artifact_digest": artifact_digest(output), "summary": summary}
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
        # Candidate-order instability always abstains. Both passes are charged.
        second = self.agent.predict(inputs, {"decision": spec.question(reverse=True)}, max_len=256) if check_order else first
        elapsed = (time.perf_counter() - start) * 1000
        answers = []
        for response in (first, second):
            if (not isinstance(response, dict) or not isinstance(response.get("answers"), dict)
                    or not isinstance(response["answers"].get("decision"), dict)):
                raise ValueError("model returned an invalid decision response")
            answers.append(response["answers"]["decision"])
        answer, other = answers
        confidences = []
        for candidate in (answer, other):
            probabilities = candidate.get("probabilities")
            if (candidate.get("choice") not in spec.choices or not isinstance(probabilities, dict)
                    or set(probabilities) != set(spec.choices)):
                raise ValueError("model returned invalid choice probabilities")
            values = list(probabilities.values())
            if any(not finite_number(p) or not 0 <= p <= 1 for p in values):
                raise ValueError("model returned invalid choice probabilities")
            if not math.isclose(sum(values), 1.0, abs_tol=0.001):
                raise ValueError("model returned unnormalized choice probabilities")
            confidence = candidate.get("answer_confidence", max(values))
            if not finite_number(confidence) or not 0 <= confidence <= 1:
                raise ValueError("model returned invalid confidence")
            confidences.append(confidence)
        choice = answer["choice"]
        confidence = min(confidences)
        stable = choice == other["choice"]
        # Missing truncation evidence cannot establish that the complete input fit.
        truncated = any(not isinstance(response.get("usage"), dict)
                        or response["usage"].get("truncated") is not False for response in (first, second))
        return {"choice": choice, "confidence": confidence, "stable": stable,
            "truncated": truncated, "duration_ms": elapsed, "probabilities": answer["probabilities"],
            "backend": self.backend}


def materialize(base: Path, head: Path, output: Path) -> None:
    """Reconstruct an adapter using only safetensors, never executable pickle weights."""
    import shutil
    import tempfile

    from safetensors.torch import load_file, save_file
    if output.exists() or output.is_symlink():
        raise ValueError("materialization output already exists")
    manifest = json.loads((head.parent / "manifest.json").read_text())
    if manifest["base_revision"] != BASE_REVISION or file_hash(head) != manifest["head_sha256"]:
        raise ValueError("adapter provenance or head digest mismatch")
    if file_hash(base / "model.safetensors") != manifest["base_weights_sha256"]:
        raise ValueError("base checkpoint does not match adapter provenance")
    if not isinstance(manifest.get("inference_artifact_digest"), str):
        raise ValueError("adapter needs a complete inference artifact digest")
    state = load_file(str(base / "model.safetensors"))
    adapted = load_file(str(head))
    expected = {k for k in state if not k.startswith("encoder.")}
    if set(adapted) != expected or any(adapted[k].shape != state[k].shape for k in expected):
        raise ValueError("head keys or shapes do not match the pinned base")
    state.update(adapted)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Verify in a disposable staging directory so failures cannot leave a policy
    # that appears complete or replace a previous valid reconstruction.
    with tempfile.TemporaryDirectory(prefix=".reflex-materialize-", dir=output.parent) as temp:
        staged = Path(temp) / "policy"
        staged.mkdir()
        for name in ("encoder", "tokenizer"):
            shutil.copytree(head.parent / name, staged / name, symlinks=True)
        for name in ("rl_agent_config.json", "manifest.json"):
            if (head.parent / name).is_symlink():
                raise ValueError("adapter metadata must be regular files")
            shutil.copy2(head.parent / name, staged / name)
        save_file(state, str(staged / "model.safetensors"))
        if (file_hash(staged / "model.safetensors") != manifest["weights_sha256"]
                or artifact_digest(staged) != manifest["inference_artifact_digest"]):
            raise ValueError("reconstructed inference artifacts do not match adapter provenance")
        if output.exists() or output.is_symlink():
            raise FileExistsError("materialization output already exists")
        staged.rename(output)
