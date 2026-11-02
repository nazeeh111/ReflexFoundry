import importlib.util
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
PUBLIC = HERE / "benchmarks/codex-e2e-v2"


def load(name: str, source: Path):
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def analyzer():
    return load("amended_analysis", HERE / "scripts/analyze_native_v2.py")


@pytest.fixture
def evidence_copy(tmp_path: Path):
    study, continuation = tmp_path / "execution", tmp_path / "continuation"
    shutil.copytree(PUBLIC / "execution", study)
    shutil.copytree(PUBLIC / "continuation", continuation)
    return study, study / "observer-provenance.json", continuation


def test_actual_observations_pairs_and_phase_qualifications(analyzer) -> None:
    data = analyzer.build(
        PUBLIC / "execution", PUBLIC / "execution/observer-provenance.json", PUBLIC / "continuation"
    )
    assert (
        data["completed_observations"],
        data["protocol_valid_observations"],
        data["independently_verified_successes"],
        data["model_inference_observations"],
        data["valid_pair_count"],
    ) == (20, 19, 19, 11, 15)
    assert data["all_twenty_results_present"] is True
    assert data["all_twenty_complete_and_protocol_valid"] is False
    assert data["source_summary_completed_at_read"] == 18
    assert "Historical phase-A" in data["source_summary_scope"]
    assert len(data["observations"]) == 20 and len(data["pairs"]) == 16
    rows = {row["index"]: row for row in data["observations"]}
    assert rows[18]["protocol_valid"] is False and rows[18]["metrics"]["input_tokens"] is None
    assert rows[18]["metrics"]["output_tokens"] is None
    assert rows[18]["phase"] == "original-study"
    assert rows[19]["phase"] == rows[20]["phase"] == "reviewed-continuation-01"
    continuation = data["continuation"]
    assert continuation["verified_phase_a_files"] == 135
    assert len(continuation["publication_only_extras"]) == 4
    assert len(continuation["supplemented_preflight_files"]) == 2
    assert continuation["publication_time_gap"] is True
    assert continuation["historical_observer_checkout"] == "10f342d0d52b26f99a54948324c96d3efa2a8a80"
    for pair in data["pairs"]:
        if pair["valid"]:
            original, candidate = rows[pair["original_index"]], rows[pair["candidate_index"]]
            for key, delta in pair["candidate_minus_original"].items():
                assert math.isclose(candidate["metrics"][key] - original["metrics"][key], delta)
        else:
            assert pair["candidate_index"] == 18 and pair["candidate_minus_original"] is None
    for summary in data["paired_summaries"]:
        pairs = [pair for pair in data["pairs"] if pair["valid"] and pair["arm"] == summary["arm"]]
        assert summary["valid_pairs"] == (3 if summary["arm"] == "ordinary-laya" else 4)
        for key in analyzer.METRICS:
            expected_original = sum(rows[pair["original_index"]]["metrics"][key] for pair in pairs) / len(
                pairs
            )
            assert math.isclose(summary["matching_original_metrics"][key]["mean"], expected_original)
    markdown, svg = analyzer.markdown(data), analyzer.svg(data)
    assert "Matched-cohort" in markdown and "unknown cause" in markdown and "publication/time gap" in markdown
    assert "matching original-agent cohorts" in svg and "not an uninterrupted study" in svg
    ET.fromstring(svg)


def test_no_continuation_preserves_original_outputs(analyzer) -> None:
    args = (PUBLIC / "execution", PUBLIC / "execution/observer-provenance.json")
    before = json.loads((PUBLIC / "analysis/analysis.json").read_text())
    after = analyzer.build(*args)
    for data in (before, after):
        data.pop("generated_utc")
        data["input_sha256"] = {name.split("/execution/", 1)[1]: value
                                for name, value in data["input_sha256"].items()}
    assert before == after
    assert analyzer.markdown(after) == (PUBLIC / "analysis/analysis.md").read_text()
    assert analyzer.svg(after) == (PUBLIC / "analysis/comparison.svg").read_text()


def test_manifest_paths_cannot_escape_root(analyzer) -> None:
    for name in ("../outside", "/absolute", "a/../b", "./plan.json", ".", "a//b", "a\\b"):
        with pytest.raises(ValueError, match="unsafe"):
            analyzer.relative_name(name)


def test_original_bytes_and_supplement_cannot_be_overwritten(analyzer, evidence_copy) -> None:
    study, provenance, continuation = evidence_copy
    target = study / "attempts/18/result.json"
    original = target.read_bytes()
    target.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="phase-A bytes"):
        analyzer.build(study, provenance, continuation)
    target.write_bytes(original)
    preflight = study / "preflight/funcy-first.json"
    preflight.parent.mkdir()
    preflight.write_bytes((continuation / "phase-a-supplement/preflight/funcy-first.json").read_bytes())
    with pytest.raises(ValueError, match="never override"):
        analyzer.build(study, provenance, continuation)


def test_driver_and_new_result_bindings_are_verified(analyzer, evidence_copy) -> None:
    study, provenance, continuation = evidence_copy
    driver = continuation / "continue_native.py"
    original = driver.read_bytes()
    driver.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="driver|continue_native.py"):
        analyzer.build(study, provenance, continuation)
    driver.write_bytes(original)
    result_file = continuation / "attempts/19/result.json"
    result = json.loads(result_file.read_text())
    result["amendment_sha256"] = "0" * 64
    result_file.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="binding differs"):
        analyzer.build(study, provenance, continuation)


def test_unregistered_files_links_and_byte_cap_are_rejected(analyzer, evidence_copy, monkeypatch) -> None:
    study, provenance, continuation = evidence_copy
    unexpected = study / "unexpected.txt"
    unexpected.write_text("not registered")
    with pytest.raises(ValueError, match="contents were not read"):
        analyzer.build(study, provenance, continuation)
    unexpected.unlink()
    link = continuation / "unexpected-link"
    link.symlink_to(continuation / "review.json")
    with pytest.raises(ValueError, match="links are forbidden"):
        analyzer.build(study, provenance, continuation)
    link.unlink()
    monkeypatch.setattr(analyzer, "MAX_EVIDENCE_BYTES", 1)
    with pytest.raises(ValueError, match="32MiB"):
        analyzer.build(study, provenance, continuation)
