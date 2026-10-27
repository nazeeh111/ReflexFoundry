import json

import pytest

from reflexfoundry.codex import summarize_events
from reflexfoundry.core import discover, observe, validate_inputs, validate_splits


def record(**updates):
    row = {"id": "a", "repository": "r", "split": "train", "spec": "test-scope-v1",
        "inputs": {"summary": "Fix display", "changed_files": ["labels.py"]},
        "selected": "focused", "authorized": True}
    return row | updates


def test_consent_and_privacy_allowlist():
    row = record(inputs={"summary": "Fix for a@example.com token=abcdefgh at /Users/person/project",
                         "changed_files": ["labels.py"]}, hidden_reasoning="private")
    with pytest.raises(ValueError):
        observe(row, False)
    filtered = observe(row, True)
    assert "a@example.com" not in json.dumps(filtered)
    assert "abcdefgh" not in json.dumps(filtered)
    assert "hidden_reasoning" not in filtered
    assert "/Users/person" not in json.dumps(filtered)


@pytest.mark.parametrize("spec,inputs", [
    ("permission-v1", {"summary": "approve"}),
    ("test-scope-v1", {"summary": "fix", "changed_files": ["../../secret"]}),
    ("test-scope-v1", {"summary": "fix", "source": "private"}),
    ("test-scope-v1", {"summary": "x" * 5000}),
])
def test_boundaries(spec, inputs):
    with pytest.raises(ValueError):
        validate_inputs(spec, inputs)


def test_leakage_rejected():
    with pytest.raises(ValueError, match="repository leakage"):
        validate_splits([record(), record(id="b", split="test", inputs={"summary": "Different"})])
    with pytest.raises(ValueError, match="identical inputs"):
        validate_splits([record(), record(id="b", repository="s", split="test")])
    assert discover([record()])[0]["status"] == "insufficient-evidence"


def test_codex_adapter_discards_text_paths_and_outputs(tmp_path):
    events = [{"type": "item.completed", "item": {"type": "command_execution",
        "command": "pytest /private/secret.py", "aggregated_output": "secret"}},
        {"type": "item.completed", "item": {"type": "reasoning", "text": "private"}}]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    with pytest.raises(ValueError):
        summarize_events(path)
    result = summarize_events(path, True)
    assert result["allowlisted_command_counts"] == {"pytest": 1}
    assert "secret" not in json.dumps(result)
    assert not result["training_labels"]


@pytest.mark.parametrize("summary", [
    'Update api_key="synthetic_private_value"',
    '{"api_key": "synthetic_private_value"}',
    "Fix password: 'synthetic_private_value'",
    'Fix password: "synthetic_private_value"',
    'API-KEY="synthetic_\\"private\\"_value"',
])
def test_quoted_assignments_are_redacted_before_storage(summary):
    filtered = observe(record(inputs={"summary": summary}), True)
    assert "synthetic" not in json.dumps(filtered)
    assert "[REDACTED]" in filtered["inputs"]["summary"]
    if summary.startswith("{"):
        assert json.loads(filtered["inputs"]["summary"]) == {"api_key": "[REDACTED]"}


@pytest.mark.parametrize("outcomes", [[], None, "invalid", {"focused": []},
    {"focused": {"success": True, "duration_ms": 1}},
    {"focused": {"success": True, "duration_ms": -1}, "full": {"success": True, "duration_ms": 2}},
])
def test_invalid_outcome_shapes_fail_without_attribute_errors(outcomes):
    with pytest.raises(ValueError, match="outcome"):
        observe(record(outcomes=outcomes), True)
    with pytest.raises(ValueError, match="outcome"):
        validate_splits([record(outcomes=outcomes)])


def test_loaded_records_report_line_and_reject_bad_metadata(tmp_path):
    from reflexfoundry.core import read_records
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(record()) + '\n["PRIVATE_INPUT"]\n')
    with pytest.raises(ValueError, match="line 2") as error:
        read_records(path)
    assert "PRIVATE_INPUT" not in str(error.value)
    with pytest.raises(ValueError, match="repository"):
        validate_splits([record(repository=[])])


def test_empty_outcomes_do_not_count_as_discovery_evidence():
    rows = [record(id=f"record-{index}", outcomes={}) for index in range(20)]
    result = discover(rows)[0]
    assert result["outcome_records"] == 0
    assert result["status"] == "insufficient-evidence"


def test_oversized_json_integer_is_a_validation_error(tmp_path):
    from reflexfoundry.core import read_records
    row = record(outcomes={"focused": {"success": True, "duration_ms": 10**400},
                           "full": {"success": True, "duration_ms": 1}})
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="finite nonnegative"):
        read_records(path)


def test_evaluation_split_validation_rejects_nonobject_rows():
    with pytest.raises(ValueError, match="record must be an object"):
        validate_splits([[]], require_evaluation_outcomes=True)
