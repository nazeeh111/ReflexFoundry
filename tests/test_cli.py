import json
from pathlib import Path

from reflexfoundry.cli import main


def test_specs_and_help_need_no_model(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["specs"]) == 0
    specs = json.loads(capsys.readouterr().out)
    assert {row["id"] for row in specs} == {"test-scope-v1", "context-route-v1"}
    assert main(["discover"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_consent_redaction_duplicate_and_discovery(tmp_path: Path, capsys) -> None:
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"id": "one", "authorized": True, "spec": "test-scope-v1",
        "inputs": {"summary": "Fix formatter; contact sample@example.com"}, "selected": "full"}))
    workspace = tmp_path / "records"
    argv = ["observe", str(source), "--workspace", str(workspace)]
    assert main(argv) == 2
    assert not (workspace / "records.jsonl").exists()
    assert main([*argv, "--consent"]) == 0
    saved = (workspace / "records.jsonl").read_text()
    assert "sample@example.com" not in saved
    assert "[EMAIL]" in saved
    assert main([*argv, "--consent"]) == 2
    assert len((workspace / "records.jsonl").read_text().splitlines()) == 1
    capsys.readouterr()
    assert main(["discover", "--workspace", str(workspace)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "insufficient-evidence"


def test_bad_input_and_small_evaluation_fail_cleanly(tmp_path: Path, capsys) -> None:
    source = tmp_path / "input.json"
    source.write_text("[]")
    assert main(["observe", str(source), "--consent"]) == 2
    assert "must be an object" in capsys.readouterr().err
    assert main(["evaluate", "--workspace", str(tmp_path), "--policy", "absent"]) == 2
    assert "at least 30" in capsys.readouterr().err


def test_activation_requires_evidence_before_optional_model(tmp_path: Path, capsys) -> None:
    assert main(["deploy", "--workspace", str(tmp_path), "--policy", "absent", "--consent"]) == 2
    assert "evaluate and register" in capsys.readouterr().err
