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
            "symbol": "Read the definition of a named source symbol",
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


def finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


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
    records = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            validate_record(record)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid decision record on line {number}: {exc}") from None
        records.append(record)
    return records


def validate_inputs(spec_id: str, inputs: Any) -> dict[str, Any]:
    if not isinstance(spec_id, str) or spec_id not in SPECS:
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
        value = re.sub(r"(?i)(?:sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{12,}|github_pat_[a-z0-9_]{12,}|bearer\s+[a-z0-9._-]+)", "[REDACTED]", value)
        assignment = r'''(?i)(\b(?:password|api[_-]?key|secret|token)["']?\s*[=:]\s*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s"',;}]+)'''
        def replace_secret(match: re.Match[str]) -> str:
            original = match[2]
            quote = original[0] if original[0] in "\"'" else ""
            return match[1] + quote + "[REDACTED]" + quote
        value = re.sub(assignment, replace_secret, value)
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[EMAIL]", value)
        return re.sub(r"/(?:Users|home)/[^/\s\"']+", "/[HOME]", value)
    return redact(inputs)


def observe(raw: dict[str, Any], consent: bool) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("observation must be an object")
    if not consent or raw.get("authorized") is not True:
        raise ValueError("explicit --consent and authorized:true are required")
    spec_id = raw.get("spec", "")
    spec = SPECS.get(spec_id) if isinstance(spec_id, str) else None
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
    if result["split"] not in ("train", "calibration", "promotion", "test", "unassigned"):
        raise ValueError("unsupported split")
    outcomes = raw.get("outcomes", {})
    validate_outcomes(spec.id, outcomes)
    if outcomes:
        result["outcomes"] = {}
        for choice in spec.choices:
            outcome = outcomes.get(choice, {})
            result["outcomes"][choice] = {"success": outcome["success"], "duration_ms": float(outcome["duration_ms"])}
    return result


def validate_outcomes(spec_id: str, outcomes: Any, required: bool = False) -> None:
    if not isinstance(outcomes, dict):
        raise ValueError("outcomes must be an object")
    if not outcomes and not required:
        return
    if set(outcomes) != set(SPECS[spec_id].choices):
        raise ValueError("outcomes must include every specification choice")
    for outcome in outcomes.values():
        if not isinstance(outcome, dict):
            raise ValueError("each outcome must be an object")
        duration: Any = outcome.get("duration_ms")
        if not isinstance(outcome.get("success"), bool) or not finite_number(duration) or duration < 0:
            raise ValueError("outcomes need boolean success and finite nonnegative duration")


def validate_record(row: Any, require_outcomes: bool = False) -> None:
    if not isinstance(row, dict):
        raise ValueError("decision record must be an object")
    spec_id = row.get("spec")
    if not isinstance(spec_id, str):
        raise ValueError("decision specification must be text")
    validate_inputs(spec_id, row.get("inputs"))
    if row.get("authorized") is not True:
        raise ValueError("decision records require explicit collection authorization")
    if row.get("selected") not in SPECS[row["spec"]].choices:
        raise ValueError("selected choice is outside specification")
    for field in ("id", "repository"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if "task_group" in row and (not isinstance(row["task_group"], str) or not row["task_group"].strip()):
        raise ValueError("task_group must be a nonempty string")
    if row.get("split") not in ("train", "calibration", "promotion", "test", "unassigned"):
        raise ValueError("unsupported split")
    validate_outcomes(row["spec"], row.get("outcomes", {}), required=require_outcomes)


def discover(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in records:
        validate_record(row)
    result = []
    for spec_id, spec in SPECS.items():
        rows = [r for r in records if r.get("spec") == spec_id]
        if not rows:
            continue
        evidence = [r for r in rows if r.get("outcomes")]
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


def validate_splits(records: list[dict[str, Any]], require_evaluation_outcomes: bool = False) -> None:
    repositories: dict[str, str] = {}
    ids: set[str] = set()
    tasks: dict[str, str] = {}
    inputs: dict[str, str] = {}
    for row in records:
        validate_record(row, require_outcomes=(require_evaluation_outcomes
                        and isinstance(row, dict) and row.get("split") != "train"))
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
    inputs = {"type": "object", "required": ["summary"], "additionalProperties": False,
              "properties": {"summary": {"type": "string", "minLength": 1},
                             "changed_files": {"type": "array", "items": {"type": "string"},
                                               "description": "Relative paths within the repository"},
                             "symbol": {"type": "string"}}}
    criteria = {
        "test-scope-v1": "The validation action's accept/reject agrees with a separate complete public-contract grader.",
        "context-route-v1": "The bounded retrieval result contains the declared target source context, checked independently of the policy.",
    }
    return [asdict(spec) | {"input_schema": inputs, "success_criterion": criteria[spec.id]}
            for spec in SPECS.values()]
