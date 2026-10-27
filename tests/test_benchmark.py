from pathlib import Path

import pytest

from reflexfoundry.benchmark import generate, heuristic, summarize


def test_executed_records_and_independent_oracle(tmp_path: Path) -> None:
    rows = generate(tmp_path / "run", {"train": 8, "test": 8})
    assert len(rows) == 16
    assert (tmp_path / "run" / "records.jsonl").is_file()
    assert (tmp_path / "run" / "manifest.json").is_file()
    assert not ({r["repository"] for r in rows if r["split"] == "train"} &
                {r["repository"] for r in rows if r["split"] == "test"})
    assert all(r["outcomes"]["full"]["success"] for r in rows)
    assert any(r["outcomes"]["focused"]["false_acceptance"] for r in rows)
    assert any(not r["oracle"]["passed"] for r in rows)
    assert all(r["outcomes"][r["selected"]]["success"] for r in rows)
    assert all(r["outcomes"][choice]["duration_ms"] > 0 for r in rows for choice in ("focused", "full"))
    assert all(set(r["inputs"]) == {"summary", "changed_files"} for r in rows)
    assert len({r["inputs"]["summary"] for r in rows}) == len(rows)
    assert all(len(r["outcomes"]["focused"]["trials_ms"]) == 3 for r in rows)
    stats = summarize(rows)
    assert stats["n"] == 16
    assert stats["policies"][0]["success_rate"] == 1


def test_conservative_heuristic() -> None:
    assert heuristic({"changed_files": ["src/units.py"]}) == "full"
    assert heuristic({"changed_files": ["src/labels.py"]}) == "focused"


def test_no_mixed_outputs_or_invalid_sizes(tmp_path: Path) -> None:
    path = tmp_path / "run"
    generate(path, {"test": 0})
    with pytest.raises(FileExistsError):
        generate(path, {"test": 0})
    with pytest.raises(ValueError):
        generate(tmp_path / "bad", {"test": True})
