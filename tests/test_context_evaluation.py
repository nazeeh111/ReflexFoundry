"""Context retrieval uses its own choices and evidence, never test-scope aliases."""
import json

import pytest

from reflexfoundry.core import digest, spec_dicts, write_json
from reflexfoundry.evaluation import evaluate, heuristic, summarize


def context_dataset():
    rows, predictions = [], {}
    for split in ("train", "calibration", "promotion", "test"):
        for index in range(40):
            key = f"{split}-{index}"
            named = index % 2 == 0
            inputs = {"summary": f"Find the source context for public query {key}."}
            if named:
                inputs["symbol"] = "public_target"
            rows.append({"id": key, "repository": key, "task_group": key, "split": split,
                         "spec": "context-route-v1", "inputs": inputs, "authorized": True,
                         "selected": "symbol" if named else "search",
                         "outcomes": {"symbol": {"success": named, "duration_ms": 10},
                                      "search": {"success": True, "duration_ms": 100}}})
            predictions[key] = {"choice": "symbol" if named else "search", "confidence": .99,
                                "stable": True, "truncated": False, "duration_ms": 1}
    return rows, predictions


def test_context_comparison_uses_retrieval_fallback_and_both_real_actions():
    rows, predictions = context_dataset()
    report = evaluate(rows, predictions, 300, "test-only")
    assert report["spec"] == "context-route-v1"
    assert "source retrieval" in report["scope"]
    assert report["decision_spec"]["fallback"] == "search"
    assert report["repository_groups"] == {"calibration": 40, "promotion": 40, "test": 40}
    policies = {item["name"]: item for item in report["policies"]}
    assert {"original-search", "always-symbol", "deterministic-heuristic", "selective"} <= policies.keys()
    assert policies["always-symbol"]["errors"] == 20
    assert policies["deterministic-heuristic"]["errors"] == 0
    assert policies["selective"]["fallback_rate"] == 1
    assert policies["selective"]["decision_counts"] == {"symbol": 0, "search": 40}
    assert not report["deployment_allowed"]


def test_context_heuristic_and_mixed_family_rejection():
    rows, predictions = context_dataset()
    assert heuristic(rows[0]) == "symbol"
    assert heuristic(rows[1]) == "search"
    mixed = rows[0] | {"spec": "test-scope-v1", "selected": "full", "outcomes": {
        "focused": {"success": True, "duration_ms": 10}, "full": {"success": True, "duration_ms": 100}}}
    with pytest.raises(ValueError, match="one decision family"):
        evaluate([mixed, *rows[1:]], predictions, 0, "test-only")
    with pytest.raises(ValueError, match="one decision family"):
        summarize([mixed, rows[1]], predictions, .9, 0)


def test_specs_expose_explicit_input_and_success_contracts():
    for spec in spec_dicts():
        assert spec["input_schema"]["additionalProperties"] is False
        assert spec["input_schema"]["required"] == ["summary"]
        assert spec["success_criterion"]


def test_failed_actions_remain_outcomes_without_fake_positive_label_metrics():
    rows, predictions = context_dataset()
    rows = [row for row in rows if row["split"] == "test"]
    for outcome in rows[0]["outcomes"].values():
        outcome["success"] = False
    result = summarize(rows, predictions, .9, 0)
    assert result["decision_label_records"] == len(rows) - 1
    assert result["decision_label_agreement"] == 1
    assert result["policies"][0]["errors"] == 1


def test_single_repository_has_no_population_uncertainty_estimate():
    rows, predictions = context_dataset()
    for row in rows:
        row["repository"] = row["split"]
    report = evaluate(rows, predictions, 300, "test-only")
    for split in ("promotion", "test"):
        assert report[split]["uncertainty_available"] is False
        assert report[split]["paired_saved_ms_95"] is None
        assert report[split]["paired_success_delta_95"] is None
        assert report[split]["paired_saved_ms_mean"] < 0
    assert report["deployment_allowed"] is False
    assert "promotion task outcomes regress" not in report["reasons"]


def test_cli_context_evaluate_registers_and_exports_without_loading_training_rows(tmp_path, monkeypatch, capsys):
    from reflexfoundry import model
    from reflexfoundry.cli import main
    rows, predictions = context_dataset()
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "records.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    policy = tmp_path / "policy"
    policy.mkdir()
    (policy / "model.safetensors").write_bytes(b"test-only, no inference")
    (policy / "rl_agent_config.json").write_text("{}")
    for directory in ("encoder", "tokenizer"):
        (policy / directory).mkdir()
        (policy / directory / "config.json").write_text("{}")
    write_json(policy / "manifest.json", {"train_digest": digest([r for r in rows if r["split"] == "train"]),
               "weights_sha256": model.file_hash(policy / "model.safetensors")})
    seen = []
    class TestPolicy:
        startup_ms = 300
        backend = "test-only"
        def __init__(self, *_args, **_kwargs):
            pass
        def predict(self, spec, inputs):
            assert spec == "context-route-v1"
            assert "train-" not in inputs["summary"]
            seen.append(inputs)
            row = next(row for row in rows if row["inputs"] == inputs)
            return predictions[row["id"]]
    monkeypatch.setattr(model, "LocalPolicy", TestPolicy)
    assert main(["evaluate", "--workspace", str(root), "--policy", str(policy)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["spec"] == "context-route-v1"
    assert len(seen) == 120
    assert main(["shadow", "--workspace", str(root), "--policy", str(policy)]) == 0
    assert main(["lab", "--workspace", str(root), "--output", str(tmp_path / "lab.html")]) == 0
    assert "original-search" in (tmp_path / "lab.html").read_text()
