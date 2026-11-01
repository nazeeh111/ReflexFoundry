import json
import re
from pathlib import Path

import pytest

from reflexfoundry.lab import build_lab

ARMS = ("original-agent", "deterministic-heuristic", "ordinary-laya", "trained-always", "selective-shadow")
METRICS = ("cli_wall_ms", "pipeline_wall_ms", "input_tokens", "cached_input_tokens", "output_tokens")


def test_matched_native_costs_exclude_failed_and_missing_observations(tmp_path: Path) -> None:
    source = analysis_fixture()
    candidate = source["observations"][2]
    candidate.update(status="protocol-valid", result_present=True, protocol_valid=True,
                     independently_verified_success=True, inference_observed=True,
                     metrics=dict(zip(METRICS, (20_000, 24_000, 150, 40, 9), strict=True)))
    source.update(completed_observations=3, protocol_valid_observations=2)
    _, data = render(tmp_path, source)
    pairs = {pair["arm"]: pair for pair in data["native"]["pairs"]}
    assert pairs["ordinary-laya"]["n"] == 1
    assert pairs["ordinary-laya"]["means"]["pipeline_wall_ms"] == 12_000
    assert pairs["ordinary-laya"]["means"]["input_tokens"] == 50
    assert pairs["deterministic-heuristic"]["n"] == 0
    assert pairs["deterministic-heuristic"]["means"]["pipeline_wall_ms"] is None


def test_amended_lab_retains_failure_and_only_displays_fixed_phase_notice(tmp_path: Path) -> None:
    source = analysis_fixture(complete=True)
    failed = source["observations"][17]
    failed.update(status="protocol-failed", protocol_valid=False, independently_verified_success=False,
                  inference_observed=False, metrics=dict(zip(METRICS, (181_000, 209_000, None, None, None), strict=True)))
    for row in source["observations"][18:]:
        row["phase"] = "reviewed-continuation-01"
    source.update(protocol_valid_observations=19, continuation={
        "phase": "reviewed-continuation-01", "indices": [19, 20], "publication_time_gap": True,
        "private_comment": "DO_NOT_EMBED_AMENDMENT_TRANSCRIPT",
    })
    html, data = render(tmp_path, source)
    assert data["native"]["amended"] is True
    assert (data["native"]["completed"], data["native"]["protocol_valid"], data["native"]["protocol_failed"]) == (20, 19, 1)
    assert data["native"]["model_inference_observations"] == 11
    assert data["native"]["complete"] is False
    assert "DO_NOT_EMBED_AMENDMENT_TRANSCRIPT" not in html


def test_declared_amendment_cannot_erase_the_original_failed_observation(tmp_path: Path) -> None:
    source = analysis_fixture(complete=True)
    for row in source["observations"][18:]:
        row["phase"] = "reviewed-continuation-01"
    source["continuation"] = {"phase": "reviewed-continuation-01", "indices": [19, 20], "publication_time_gap": True}
    with pytest.raises(ValueError, match="original failed observation"):
        render(tmp_path, source)


def analysis_fixture(*, complete: bool = False) -> dict:
    observations = []
    for repeat in (1, 2):
        for task in ("funcy-first", "cachetools-getitem"):
            for arm in ARMS:
                index = len(observations) + 1
                valid = complete or index == 1
                failed = not complete and index == 2
                observations.append({
                    "index": index, "task": task, "repeat": repeat, "arm": arm,
                    "status": "protocol-valid" if valid else "protocol-failed" if failed else "missing",
                    "result_present": valid or failed, "protocol_valid": valid,
                    "independently_verified_success": True if valid else False if failed else None,
                    "inference_observed": valid and arm in ARMS[2:],
                    "metrics": dict(zip(METRICS, (10_000, 12_000, 100, 40, 7), strict=True)) if valid else
                               {key: 20_000 if failed and key.endswith("ms") else None for key in METRICS},
                    "independent": {"output": "PRIVATE_TRANSCRIPT_DO_NOT_DISPLAY"},
                })
    return {"format": 1, "planned_observations": 20, "completed_observations": 20 if complete else 2,
            "protocol_valid_observations": 20 if complete else 1, "planned_repository_groups": 2,
            "all_twenty_complete_and_protocol_valid": True,
            "status": "FINAL DESCRIPTIVE SNAPSHOT", "observations": observations,
            "input_sha256": {"/private/sensitive-source.py": "DO_NOT_DISPLAY_SOURCE_PATH"},
            "execution_provenance": {"raw": "DO_NOT_DISPLAY_PRIVATE_PROVENANCE"},
            "raw_source": "DO_NOT_DISPLAY_PRIVATE_CODE"}


def render(tmp_path: Path, source: dict | None) -> tuple[str, dict]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if source is not None:
        (workspace / "native-study.json").write_text(json.dumps(source))
    output = build_lab(workspace, tmp_path / "output.html")
    html = output.read_text()
    match = re.search(r'<script type="application/json" id="reflex-data">(.*?)</script>', html, re.DOTALL)
    assert match
    return html, json.loads(match.group(1))


def test_default_lab_keeps_native_section_hidden(tmp_path: Path) -> None:
    html, data = render(tmp_path, None)
    assert data["native"] is None
    assert '<section class="section" id="native-comparison" hidden>' in html
    assert 'id="native-nav" hidden' in html
    assert data["evaluation"] == {} and data["deployment"] == {} and data["records"] == []


def test_partial_failure_is_visible_and_raw_analysis_is_not_embedded(tmp_path: Path) -> None:
    html, data = render(tmp_path, analysis_fixture())
    native = data["native"]
    assert (native["completed"], native["planned"], native["protocol_valid"], native["protocol_failed"]) == (2, 20, 1, 1)
    assert native["complete"] is False  # Ignore a false free-text/final-flag claim.
    assert len(native["arms"]) == 5
    heuristic = next(row for row in native["arms"] if row["arm"] == "deterministic-heuristic")
    assert heuristic["completed"] == heuristic["protocol_failed"] == 1
    assert heuristic["independent_checked"] == 1 and heuristic["independent_successes"] == 0
    assert all(value is None for value in heuristic["means"].values())
    original = next(row for row in native["arms"] if row["arm"] == "original-agent")
    assert original["means"]["input_tokens"] == 100
    assert original["means"]["cached_input_tokens"] == 40  # Cached is never added to input.
    for marker in ("PRIVATE_TRANSCRIPT", "DO_NOT_DISPLAY", "/private/sensitive-source.py"):
        assert marker not in html
    assert "Partial comparison" in html and "Agent-side internal check execution" in html
    assert "Only two repository groups" in html and "shared original-agent baselines" in html
    assert "innerHTML" not in html
    assert 'aria-label="Native agent comparison table" tabindex="0"' in html


def test_complete_counts_and_inference_are_derived_from_rows(tmp_path: Path) -> None:
    fixture = analysis_fixture(complete=True)
    fixture["all_twenty_complete_and_protocol_valid"] = False
    _, data = render(tmp_path, fixture)
    native = data["native"]
    assert native["complete"] is True
    assert native["model_inference_observations"] == 12
    assert all(row["completed"] == row["planned"] == row["protocol_valid"] == 4 for row in native["arms"])


@pytest.mark.parametrize("change", ["duplicate", "unknown-arm", "unhashable-task", "nan", "negative", "boolean", "cached-exceeds-input"])
def test_malformed_native_evidence_fails_before_export(tmp_path: Path, change: str) -> None:
    fixture = analysis_fixture()
    row = fixture["observations"][0]
    if change == "duplicate":
        fixture["observations"][1]["index"] = row["index"]
    elif change == "unknown-arm":
        row["arm"] = "arbitrary-private-policy"
    elif change == "unhashable-task":
        row["task"] = []
    elif change == "cached-exceeds-input":
        row["metrics"]["cached_input_tokens"] = 101
    else:
        row["metrics"]["cli_wall_ms"] = {"nan": float("nan"), "negative": -1, "boolean": True}[change]
    with pytest.raises(ValueError):
        render(tmp_path, fixture)
    assert not (tmp_path / "output.html").exists()


def test_native_file_limit_and_links_are_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "native-study.json"
    source.write_text(" " * (512 * 1024 + 1))
    with pytest.raises(ValueError, match="512 KiB"):
        build_lab(workspace, tmp_path / "too-large.html")
    source.unlink()
    source.symlink_to(workspace / "absent.json")
    with pytest.raises(ValueError, match="not a link"):
        build_lab(workspace, tmp_path / "linked.html")


def test_native_and_existing_payload_cannot_terminate_json_script(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = analysis_fixture()
    attack = '</script><script>globalThis.UNTRUSTED=1</script>&'
    fixture["raw_source"] = attack
    (workspace / "native-study.json").write_text(json.dumps(fixture))
    (workspace / "evaluation.json").write_text(json.dumps({"scope": attack}))
    output = build_lab(workspace, tmp_path / "safe.html").read_text()
    assert attack not in output
    assert r"\u003c/script\u003e" in output and r"\u0026" in output
    assert output.count('<script type="application/json" id="reflex-data">') == 1
