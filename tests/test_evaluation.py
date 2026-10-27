import pytest

from reflexfoundry.evaluation import calibrate, choose, evaluate, wilson_upper


def dataset():
    rows, predictions = [], {}
    for split in ("train", "calibration", "promotion", "test"):
        for i in range(40):
            key = f"{split}-{i}"
            rows.append({"id": key, "repository": key, "split": split, "spec": "test-scope-v1",
                "selected": "focused", "authorized": True, "inputs": {"summary": "Fix display " + key},
                "outcomes": {"focused": {"success": True, "duration_ms": 10},
                             "full": {"success": True, "duration_ms": 100}}})
            predictions[key] = {"choice": "focused", "confidence": .99, "stable": True,
                                "truncated": False, "duration_ms": 1}
    return rows, predictions


def test_small_calibration_refuses_false_certainty():
    rows, predictions = dataset()
    cal = [r for r in rows if r["split"] == "calibration"]
    assert calibrate(cal[:5], predictions)["threshold"] > 1
    assert wilson_upper(0, 5) > .4
    with pytest.raises(ValueError):
        calibrate(rows, predictions)


@pytest.mark.parametrize("update", [
    {"stable": False}, {"truncated": True}, {"confidence": .2},
    {"duration_ms": 1000}, {"choice": "approve"}, {"confidence": float("nan")},
])
def test_abstention(update):
    prediction = {"choice": "focused", "confidence": .99, "stable": True,
                  "truncated": False, "duration_ms": 1} | update
    assert choose(prediction, "test-scope-v1", .9) == ("full", True)


def test_economics_and_heuristic_block_deployment():
    rows, predictions = dataset()
    report = evaluate(rows, predictions, 100000, "hash")
    assert not report["deployment_allowed"]
    assert any("time improvement" in r for r in report["reasons"])
    assert any("heuristic" in r for r in report["reasons"])


def test_test_regression_vetoes_without_retuning():
    rows, predictions = dataset()
    # Give heuristic a strong full-scope preference so this tests the safety veto.
    for row in rows:
        row["inputs"]["summary"] += " shared contract"
        if row["split"] == "test":
            row["outcomes"]["focused"]["success"] = False
    report = evaluate(rows, predictions, 0, "hash")
    assert not report["deployment_allowed"]
    assert report["calibration"]["threshold"] == .5
    assert report["test"]["wrong_decisions"]
