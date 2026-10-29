"""Static action counts must not invent telemetry from shell text or secrets."""
import json
from pathlib import Path

import pytest

from reflexfoundry.codex import EventSummary, command_names, summarize_events, token_usage


@pytest.mark.parametrize(("command", "expected"), [
    ("pytest tests/x.py", ["pytest"]),
    ('/bin/zsh -lc "pytest tests/x.py"', ["pytest"]),
    ("/bin/bash -c 'rg needle src; pytest -q'", ["rg", "pytest"]),
    ("sh -lc 'git status&&pytest -q||rg failure .|python3 -m json.tool'", ["git", "pytest", "rg", "python3"]),
    ('''sh -c 'bash -lc "pytest tests/x.py"' ''', ["pytest"]),
    ("/usr/bin/python3 -c 'print(\"pytest tests/x.py\")'", ["python3"]),
    ("echo 'pytest tests/x.py'", []),
    ("echo ';' pytest", []),
    ("echo '&&' pytest", []),
    ("printf '%s' 'git status; pytest'", []),
    ("sh script.sh pytest", []),
    ("bash -l script.sh pytest", []),
    ("env LABEL=pytest echo hello", []),
    ("LABEL=pytest", []),
    ("LABEL=pytest pytest x.py", []),
    ("echo hi >pytest", []),
    ("echo hi 2>pytest", []),
    ("echo hi >'out;pytest'", []),
    ("<pytest echo hi", []),
    ("pytest >report.txt; rg output report.txt", ["pytest", "rg"]),
    ("echo hi;pytest tests/x.py;", ["pytest"]),
    ("echo hi\\;pytest tests/x.py", []),
    ("# pytest\nrg needle .", ["rg"]),
    ("pytest # rg secret\n git status", ["pytest", "git"]),
    ("echo $(pytest tests/x.py); rg needle .", []),
    ("echo `pytest tests/x.py`", []),
    ("$BINARY pytest", []),
    ("pytest '$HOME'", ["pytest"]),
    ('pytest "$HOME"', []),
    ("cat <<EOF\npytest tests/x.py\nEOF", []),
    ("pytest <<'EOF'\nrg text\nEOF", []),
    ("if true; pytest; fi", []),
    ("for x in pytest; do rg text; done", []),
    ("(pytest)", []),
    ("pytest &&", []),
    ("&& pytest", []),
    ("pytest | | rg .", []),
    ("pytest 'unterminated", []),
    ('pytest \\', []),
    ("", []),
])
def test_conservative_static_command_names(command: str, expected: list[str]) -> None:
    assert command_names(command) == expected


def test_nesting_and_command_size_are_bounded() -> None:
    import shlex
    command = "pytest tests/x.py"
    for _ in range(3):
        command = "sh -c " + shlex.quote(command)
    assert command_names(command) == ["pytest"]
    assert command_names("sh -c " + shlex.quote(command)) == []
    assert command_names("pytest " + "x" * 65536) == []
    with pytest.raises(ValueError, match="command must be text"):
        command_names(None)  # type: ignore[arg-type]


def test_wrapped_commands_are_counted_without_retaining_private_text(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = [
        {"type": "thread.started", "thread_id": "PRIVATE-THREAD"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "PRIVATE-MESSAGE"}},
        {"type": "item.completed", "item": {"type": "command_execution",
            "command": '/bin/zsh -lc "pytest tests/PRIVATE-PATH.py&&rg PRIVATE-TERM ."',
            "aggregated_output": "PRIVATE-OUTPUT", "exit_code": 0}},
        {"type": "item.completed", "item": {"type": "command_execution",
            "command": "echo 'pytest PRIVATE-SECRET'"}},
    ]
    path.write_text("\n".join(json.dumps(event) for event in events))
    with pytest.raises(ValueError, match="consent"):
        summarize_events(path)
    result = summarize_events(path, consent=True)
    assert result["observable_commands"] == 2
    assert result["allowlisted_command_counts"] == {"pytest": 1, "rg": 1}
    assert result["training_labels"] is False
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize(("event", "message"), [
    ([], "event at line 1 must be an object"),
    (None, "event at line 1 must be an object"),
    ({}, "event type at line 1 must be text"),
    ({"type": 7}, "event type at line 1 must be text"),
    ({"type": "item.completed"}, "completed item at line 1 must be an object"),
    ({"type": "item.completed", "item": "PRIVATE"}, "completed item at line 1 must be an object"),
    ({"type": "item.completed", "item": []}, "completed item at line 1 must be an object"),
    ({"type": "item.completed", "item": {}}, "item type at line 1 must be text"),
    ({"type": "item.completed", "item": {"type": "command_execution", "command": []}},
     "command at line 1 must be text"),
    ({"type": "item.completed", "item": {"type": "command_execution", "command": None}},
     "command at line 1 must be text"),
])
def test_malformed_events_raise_clear_errors_without_data(tmp_path: Path, event, message: str) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(event))
    with pytest.raises(ValueError) as raised:
        summarize_events(path, consent=True)
    assert str(raised.value) == message
    assert "PRIVATE" not in str(raised.value)


def test_malformed_json_does_not_echo_source(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("\nPRIVATE-SECRET invalid json")
    with pytest.raises(ValueError, match="invalid JSON event at line 2") as raised:
        summarize_events(path, consent=True)
    assert "PRIVATE" not in str(raised.value)


def test_usage_counts_never_retain_messages_or_unknown_fields() -> None:
    summary = EventSummary()
    summary.observe({"type": "item.completed", "item": {"type": "reasoning", "text": "PRIVATE-REASONING"}})
    summary.observe({"type": "turn.completed", "usage": {
        "input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20,
        "reasoning_output_tokens": 5, "unknown": "PRIVATE-SECRET"}})
    summary.observe({"type": "turn.completed", "usage": {
        "input_tokens": 50, "cached_input_tokens": 0, "output_tokens": 10,
        "reasoning_output_tokens": 0}})
    result = summary.result()
    assert result["completed_turns"] == 2
    assert result["token_usage"] == {"input_tokens": 150, "cached_input_tokens": 80,
                                    "output_tokens": 30, "reasoning_output_tokens": 5}
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("input_tokens", True), ("input_tokens", -1),
    ("input_tokens", 1.5), ("input_tokens", "100"), ("input_tokens", 2**63),
    ("cached_input_tokens", 101), ("reasoning_output_tokens", 21), ("output_tokens", None)])
def test_invalid_usage_is_unavailable_instead_of_zero(field, value) -> None:
    summary = EventSummary()
    usage = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 20}
    summary.observe({"type": "turn.completed", "usage": usage | {field: value}})
    assert summary.result()["token_usage"] is None
    assert summary.result()["invalid_usage_events"] == 1
    with pytest.raises(ValueError):
        token_usage(usage | {field: value})


def test_missing_usage_or_optional_counter_is_not_invented() -> None:
    summary = EventSummary()
    assert summary.result()["token_usage"] is None
    summary.observe({"type": "turn.completed", "usage": {
        "input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5}})
    assert summary.result()["token_usage"] == {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5}
    summary.observe({"type": "turn.completed"})
    assert summary.result()["token_usage"] is None
