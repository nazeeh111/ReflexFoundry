"""Bounded raw-model choice diagnostics; no policy deployment or native agent call.

Aliases expand the option list, not the underlying action set. Retained outcomes
measure context coverage, never coding-repair success. This script never changes
SPECS, a policy report, model originals, or native-study preparation.
"""
from __future__ import annotations

import argparse
import gc
import importlib.metadata
import itertools
import json
import math
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from reflexfoundry.core import SPECS, digest, finite_number, read_records, write_json  # noqa: E402
from reflexfoundry.model import LocalPolicy, artifact_digest, file_hash  # noqa: E402

DATA_SHA = "8c80ebfe7b11913a5983e8f0826f4ce6f41f32e26c0518cee5f8ef2a46401dfb"
MAX_LEN = 256


def conditions() -> list[dict[str, Any]]:
    original = SPECS["context-route-v1"].question()
    canonical = original["criteria"]
    parallel = {"symbol": "Retrieve source context by reading the named symbol's definition.",
                "search": "Retrieve source context by searching repository text and paths."}
    expanded = {"symbol": canonical["symbol"], "search": canonical["search"],
                "symbol_duplicate": canonical["symbol"], "search_duplicate": canonical["search"]}
    values = []
    for name, criteria in (("canonical-two", canonical), ("parallel-wording-two", parallel),
                           ("redundant-four", expanded)):
        keys = list(criteria)
        orders = [keys, keys[::-1]] if len(keys) == 2 else [keys[i:] + keys[:i] for i in range(4)]
        values.append({"name": name, "question_type": original["type"], "instructions": original["instructions"],
                       "criteria": criteria, "orders": orders,
                       "all_possible_orders": math.factorial(len(keys)),
                       "action_mapping": {key: key.split("_", 1)[0] for key in keys}})
    return values


def sample(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["split"] == "test" and row["spec"] == "context-route-v1":
            groups[row["task_group"]].append(row)
    selected: list[dict[str, Any]] = []
    for group in sorted(groups):
        items = sorted(groups[group], key=lambda row: row["id"])
        if len(items) < 2:
            raise ValueError("each test group needs at least two distinct IDs")
        selected.extend(items[index] for index in (0, -1))
    if len(groups) != 6 or len(selected) != 12 or len({row["repository"] for row in selected}) != 1:
        raise ValueError("this fixed study requires six target groups/twelve inputs from one actual repository")
    return [{key: row[key] for key in ("id", "task_group", "repository", "inputs", "outcomes")} for row in selected]


def versions() -> dict[str, str]:
    return {"python": sys.version.split()[0], **{name: importlib.metadata.version(name)
            for name in ("laya", "torch", "transformers", "tokenizers")}}


def prepare(records: Path, models: dict[str, Path], output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("prepare into a fresh study version")
    if file_hash(records) != DATA_SHA:
        raise ValueError("retained dataset differs from the fixed public context study")
    selected = sample(read_records(records))
    variants = conditions()
    plan = {"format": 1, "status": "frozen-before-inference", "script_sha256": file_hash(Path(__file__)),
            "records_sha256": DATA_SHA, "runtime_versions": versions(), "backend": "torch", "max_len": MAX_LEN,
            "models": {name: artifact_digest(path) for name, path in models.items()},
            "model_order": list(models),
            "condition_schedule": "Plan condition order on even input_index+model_index, reversed on odd; each condition's listed orders run in sequence.",
            "inputs": selected, "conditions": variants,
            "planned_predictions": len(selected) * sum(len(value["orders"]) for value in variants) * len(models),
            "sampling": "First and last lexicographic ID in each test task_group; no model-output-dependent selection.",
            "limits": ["Post-hoc exploratory reuse of public retained test inputs; no fresh heldout tasks.",
                       "Twelve inputs, six correlated symbol groups, one actual cachetools repository; no population confidence interval.",
                       "Four-choice condition adds exact semantic aliases, not new tools/actions; four of24 permutations only.",
                       "Outcome lookup is previously measured context coverage, not fresh retrieval or coding-repair success.",
                       "Winner remains the model's individual option; summed action probability is a separate diagnostic.",
                       "Retain malformed responses, missing usage and truncation; no retries, tuning, training or policy promotion.",
                       "Model startup and per-query timings are diagnostic; concurrent host load is uncontrolled; no speed/cost claim."]}
    output.mkdir(parents=True)
    write_json(output / "plan.json", plan)
    return plan


def parse_response(response: Any, condition: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise ValueError("missing answer mapping")
    answer = response["answers"].get("decision")
    if not isinstance(answer, dict):
        raise ValueError("missing decision answer")
    probabilities = answer.get("probabilities")
    keys = set(condition["criteria"])
    if (not isinstance(answer.get("choice"), str) or answer["choice"] not in keys
            or not isinstance(probabilities, dict) or set(probabilities) != keys):
        raise ValueError("choice/probability keys do not match the frozen condition")
    if (any(not finite_number(value) or not 0 <= value <= 1 for value in probabilities.values())
            or not math.isclose(sum(probabilities.values()), 1.0, abs_tol=.001)):
        raise ValueError("invalid normalized probabilities")
    usage = response.get("usage")
    truncated = usage["truncated"] if isinstance(usage, dict) and isinstance(usage.get("truncated"), bool) else None
    mapping = condition["action_mapping"]
    mass = {action: sum(value for key, value in probabilities.items() if mapping[key] == action)
            for action in ("symbol", "search")}
    # Do not replace the actual selected option/action with the aggregate winner.
    mass_winner = None if math.isclose(mass["symbol"], mass["search"], abs_tol=1e-9) else max(mass, key=lambda key: mass[key])
    return {"choice": answer["choice"], "action": mapping[answer["choice"]],
            "probabilities": probabilities, "action_probability_mass": mass,
            "summed_mass_winner": mass_winner, "truncated": truncated}


def summarize(plan: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {(model, row["id"], condition["name"], index)
                for model, row, condition in itertools.product(plan["models"], plan["inputs"], plan["conditions"])
                for index in range(len(condition["orders"]))}
    actual = [(row["model"], row["input_id"], row["condition"], row["order_index"]) for row in observations]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("every planned observation must appear exactly once")
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_key[row["model"], row["input_id"], row["condition"]].append(row)
    per_input = []
    for (model, input_id, name), rows in sorted(by_key.items()):
        valid = [row for row in rows if row["error"] is None]
        baseline = next(row for row in by_key[model, input_id, "canonical-two"] if row["order_index"] == 0)
        first = next(row for row in rows if row["order_index"] == 0)
        per_input.append({"model": model, "input_id": input_id, "condition": name,
            "planned_orders": len(rows), "valid_responses": len(valid),
            "truncated_responses": sum(row["prediction"]["truncated"] for row in valid),
            "alias_flip_observed": len({row["prediction"]["choice"] for row in valid}) > 1,
            "action_flip_observed": len({row["prediction"]["action"] for row in valid}) > 1,
            "first_order_changed_action_vs_canonical": None if baseline["error"] or first["error"] else
                first["prediction"]["action"] != baseline["prediction"]["action"],
            "retained_context_covered_observations": sum(row["retained_context_covered"] for row in valid),
            "mass_winner_differs_from_selected_action": sum(
                row["prediction"]["summed_mass_winner"] is not None and
                row["prediction"]["summed_mass_winner"] != row["prediction"]["action"] for row in valid)})
    groups = []
    for model, condition in itertools.product(plan["models"], plan["conditions"]):
        rows = [row for row in per_input if row["model"] == model and row["condition"] == condition["name"]]
        groups.append({"model": model, "condition": condition["name"], "input_count": len(rows),
            "inputs_with_observed_action_flip": sum(row["action_flip_observed"] for row in rows),
            "inputs_with_observed_alias_flip": sum(row["alias_flip_observed"] for row in rows),
            "inputs_first_order_action_changed": sum(row["first_order_changed_action_vs_canonical"] is True for row in rows),
            "inputs_with_missing_or_truncated_observation": sum(row["valid_responses"] != row["planned_orders"] or
                row["truncated_responses"] > 0 for row in rows)})
    return {"planned_predictions": plan["planned_predictions"], "retained_predictions": len(observations),
            "incomplete_or_invalid_predictions": sum(row["error"] is not None for row in observations),
            "missing_usage_predictions": sum(row["error"] == "missing_usage" for row in observations),
            "malformed_predictions": sum(row["error"] == "malformed_response" for row in observations),
            "inference_errors": sum(row["error"] == "inference_error" for row in observations),
            "actual_repository_groups": 1, "target_groups": 6, "distinct_inputs": 12,
            "population_confidence_interval": None, "aggregate": groups, "per_input": per_input,
            "native_codex_calls": 0, "deployment": "withheld; this diagnostic never changes policy eligibility",
            "limits": plan["limits"]}


def run(plan_file: Path, records: Path, models: dict[str, Path]) -> dict[str, Any]:
    output = plan_file.parent
    if (output / "observations.jsonl").exists():
        raise FileExistsError("observation ledger exists; no overwrite, retry or resumed resampling")
    plan_bytes = plan_file.read_bytes()
    plan = json.loads(plan_bytes)
    if (file_hash(records) != plan["records_sha256"] or sample(read_records(records)) != plan["inputs"]
            or file_hash(Path(__file__)) != plan["script_sha256"] or versions() != plan["runtime_versions"]
            or conditions() != plan["conditions"] or MAX_LEN != plan["max_len"]):
        raise ValueError("frozen source, inputs, conditions or runtime changed")
    if (list(models) != plan["model_order"]
            or {name: artifact_digest(path) for name, path in models.items()} != plan["models"]):
        raise ValueError("model identity changed")
    observations, startups = [], {}
    started = time.perf_counter()
    ledger = output / "observations.jsonl"
    # A fresh ledger reserves the only attempt even if loading fails.
    with ledger.open("x") as handle, tempfile.TemporaryDirectory(prefix="reflex-choice-stress-") as directory:
        for model_index, (name, source) in enumerate(models.items()):
            copied = Path(directory) / name
            shutil.copytree(source, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            before = artifact_digest(copied)
            policy = LocalPolicy(copied, backend="torch")
            startups[name] = policy.startup_ms
            if artifact_digest(copied) != before:
                raise ValueError("loader mutated the model copy; explicit conversion/re-freeze required")
            for row_index, row in enumerate(plan["inputs"]):
                variants = plan["conditions"] if (row_index + model_index) % 2 == 0 else plan["conditions"][::-1]
                for condition in variants:
                    for index, order in enumerate(condition["orders"]):
                        question = {"type": condition["question_type"], "instructions": condition["instructions"],
                                    "criteria": {key: condition["criteria"][key] for key in order}}
                        prediction, error = None, None
                        call_started = time.perf_counter()
                        try:
                            raw = policy.agent.predict(row["inputs"], {"decision": question}, max_len=MAX_LEN)
                        except Exception:
                            error = "inference_error"  # Never retain unknown model/exception text.
                        else:
                            try:
                                prediction = parse_response(raw, condition)
                            except (ValueError, TypeError, KeyError, OverflowError):
                                error = "malformed_response"
                            if prediction is not None and prediction["truncated"] is None:
                                error = "missing_usage"
                        observed = {"model": name, "input_id": row["id"], "condition": condition["name"],
                            "order_index": index, "choice_order": order, "question_digest": digest([question, order]),
                            "duration_ms": (time.perf_counter() - call_started) * 1000, "prediction": prediction,
                            "error": error, "retained_context_covered": None if prediction is None else
                                row["outcomes"][prediction["action"]]["success"]}
                        observations.append(observed)
                        handle.write(json.dumps(observed, allow_nan=False) + "\n")
                        handle.flush()
                print(json.dumps({"model": name, "completed_inputs": row_index + 1, "total_inputs": len(plan["inputs"])}), flush=True)
            del policy
            gc.collect()
            if artifact_digest(copied) != before or artifact_digest(source) != plan["models"][name]:
                raise ValueError("model inference inputs changed during diagnostic")
    if (plan_file.read_bytes() != plan_bytes or file_hash(records) != plan["records_sha256"]
            or file_hash(Path(__file__)) != plan["script_sha256"] or versions() != plan["runtime_versions"]
            or {name: artifact_digest(path) for name, path in models.items()} != plan["models"]):
        raise ValueError("plan, source, runtime, records or original models changed during diagnostic")
    result = summarize(plan, observations)
    result.update(plan_sha256=file_hash(plan_file), observations_sha256=file_hash(ledger),
                  startup_ms=startups, experiment_wall_ms=(time.perf_counter() - started) * 1000,
                  model_originals_unchanged=True, plan_unchanged=True)
    write_json(output / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--run", action="store_true")
    parser.add_argument("--records", type=Path, default=PROJECT / "benchmarks/context-v1/scoped-v1/records.jsonl")
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--trained", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = {"ordinary-laya": args.base.resolve(), "outcome-trained": args.trained.resolve()}
    result = prepare(args.records.resolve(), models, args.output.resolve()) if args.prepare_only else run(
        args.output.resolve() / "plan.json", args.records.resolve(), models)
    print(json.dumps({key: result[key] for key in ("planned_predictions",)}, indent=2))


if __name__ == "__main__":
    main()
