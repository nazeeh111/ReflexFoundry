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
