"""Typed decisions, consented observation and outcome evidence. No tool execution."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DecisionSpec:
    id: str
    purpose: str
    choices: tuple[str, ...]
    fallback: str
    max_input_bytes: int = 4096
    budget_ms: float = 250.0
    risk: str = "advisory"

    def question(self, reverse: bool = False) -> dict[str, Any]:
        descriptions = {
            "focused": "Validate only the changed module's focused tests",
            "full": "Validate all modules with the complete test suite",
            "symbol": "Read the definition and references of a named source symbol",
            "search": "Search the repository for relevant source text and paths",
        }
        choices = self.choices[::-1] if reverse else self.choices
        return {"type": "choice", "instructions": self.purpose,
                "criteria": {c: descriptions[c] for c in choices}}


SPECS = {
    "test-scope-v1": DecisionSpec("test-scope-v1",
        "Choose validation scope that preserves correct accept or reject of this coding change.",
        ("focused", "full"), "full"),
    "context-route-v1": DecisionSpec("context-route-v1",
        "Choose the first source retrieval action for the coding task.", ("symbol", "search"), "search"),
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, value: Any) -> None:
    """Atomic writes prevent an interrupted update from truncating the last valid state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".reflex-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("record file exceeds 32 MiB; split the dataset")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate_inputs(spec_id: str, inputs: Any) -> dict[str, Any]:
    if spec_id not in SPECS:
        raise ValueError("unsupported decision spec; permission and security decisions are forbidden")
    if not isinstance(inputs, dict) or set(inputs) - {"summary", "changed_files", "symbol"}:
        raise ValueError("inputs allow only summary, changed_files and symbol")
    if not isinstance(inputs.get("summary"), str) or not inputs["summary"].strip():
        raise ValueError("summary must be a nonempty string")
    files = inputs.get("changed_files", [])
    if not isinstance(files, list) or any(not isinstance(p, str) for p in files):
        raise ValueError("changed_files must be a list of relative paths")
    for p in files:
        if Path(p).is_absolute() or ".." in Path(p).parts or "\\" in p:
            raise ValueError("changed_files must stay within the repository")
    if "symbol" in inputs and not isinstance(inputs["symbol"], str):
        raise ValueError("symbol must be text")
    if len(json.dumps(inputs).encode()) > SPECS[spec_id].max_input_bytes:
        raise ValueError("input exceeds the decision's byte budget")
    return inputs


def privacy_filter(inputs: dict[str, Any]) -> dict[str, Any]:
    """Allowlist plus conservative redaction; user still reviews consented source data."""
    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        if not isinstance(value, str):
            return value
        value = re.sub(r"(?i)(?:sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{12,}|bearer\s+[a-z0-9._-]+)", "[REDACTED]", value)
        value = re.sub(r"(?i)(password|api_key|secret|token)\s*[=:]\s*[^\s\",}]+", r"\1=[REDACTED]", value)
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[EMAIL]", value)
        return re.sub(r"/(?:Users|home)/[^/\s\"']+", "/[HOME]", value)
    return redact(inputs)


def observe(raw: dict[str, Any], consent: bool) -> dict[str, Any]:
    if not consent or raw.get("authorized") is not True:
        raise ValueError("explicit --consent and authorized:true are required")
    spec = SPECS.get(raw.get("spec", ""))
    if not spec:
        raise ValueError("unsupported decision specification")
    inputs = privacy_filter(validate_inputs(spec.id, raw.get("inputs")))
    if raw.get("selected") not in spec.choices:
        raise ValueError("selected choice is outside the specification")
    # Only public identifiers and measured scalar outcomes survive ingestion.
    result: dict[str, Any] = {"id": digest([spec.id, inputs, str(raw.get("id", ""))])[:20],
        "spec": spec.id, "inputs": inputs, "selected": raw["selected"], "authorized": True,
        "repository": hashlib.sha256(str(raw.get("repository", "unknown")).encode()).hexdigest()[:16],
        "split": raw.get("split", "unassigned"), "source": "consented-observation",
        "task_group": hashlib.sha256(str(raw.get("task_group", raw.get("id", "unknown"))).encode()).hexdigest()[:20]}
    if result["split"] not in {"train", "calibration", "promotion", "test", "unassigned"}:
        raise ValueError("unsupported split")
    outcomes = raw.get("outcomes", {})
    if outcomes:
        result["outcomes"] = {}
        for choice in spec.choices:
            outcome = outcomes.get(choice, {})
            ms = outcome.get("duration_ms")
            if not isinstance(outcome.get("success"), bool) or isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms) or ms < 0:
                raise ValueError("each outcome needs a boolean success and finite nonnegative duration_ms")
            result["outcomes"][choice] = {"success": outcome["success"], "duration_ms": float(ms)}
    return result


def discover(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for spec_id, spec in SPECS.items():
        rows = [r for r in records if r.get("spec") == spec_id]
        if not rows:
            continue
        evidence = [r for r in rows if "outcomes" in r]
        opportunities = [max(0.0, r["outcomes"][spec.fallback]["duration_ms"] -
            min(o["duration_ms"] for o in r["outcomes"].values() if o["success"]))
            for r in evidence if any(o["success"] for o in r["outcomes"].values())]
        result.append({"spec": spec_id, "records": len(rows),
            "repositories": len({r["repository"] for r in rows}),
            "choice_counts": dict(Counter(r["selected"] for r in rows)),
            "outcome_records": len(evidence),
            "upper_bound_saved_ms_per_decision": sum(opportunities) / max(1, len(opportunities)),
            "status": "candidate" if len(rows) >= 20 and len(evidence) >= 20 else "insufficient-evidence",
            "note": "Oracle upper bound before inference, training and fallback costs; not measured savings."})
    return result


def validate_splits(records: list[dict[str, Any]]) -> None:
    repositories: dict[str, str] = {}
    ids: set[str] = set()
    tasks: dict[str, str] = {}
    inputs: dict[str, str] = {}
    for row in records:
        validate_inputs(row["spec"], row["inputs"])
        if row.get("authorized") is not True:
            raise ValueError("evaluation records require explicit collection authorization")
        if row.get("selected") not in SPECS[row["spec"]].choices:
            raise ValueError("selected choice is outside specification")
        outcomes = row.get("outcomes", {})
        if outcomes:
            if set(outcomes) != set(SPECS[row["spec"]].choices):
                raise ValueError("outcome choices do not match specification")
            for outcome in outcomes.values():
                duration = outcome.get("duration_ms")
                if (not isinstance(outcome.get("success"), bool) or isinstance(duration, bool)
                        or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0):
                    raise ValueError("outcomes need boolean success and finite nonnegative duration")
        split, repo = row["split"], row["repository"]
        if split not in {"train", "calibration", "promotion", "test"}:
            raise ValueError("assign records to train/calibration/promotion/test before evaluation")
        if repositories.setdefault(repo, split) != split:
            raise ValueError("repository leakage across splits")
        task = row.get("task_group", row["id"])
        if tasks.setdefault(task, split) != split:
            raise ValueError("task-group leakage across splits")
        if row["id"] in ids:
            raise ValueError("duplicate record id")
        ids.add(row["id"])
        signature = digest([row["spec"], row["inputs"]])
        if inputs.setdefault(signature, split) != split:
            raise ValueError("identical inputs leak across splits")


def spec_dicts() -> list[dict[str, Any]]:
    return [asdict(s) for s in SPECS.values()]
