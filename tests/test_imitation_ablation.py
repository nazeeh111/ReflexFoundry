"""The matched cohort must not leak outcomes into imitation targets."""
import copy
import importlib.util
from pathlib import Path

import pytest

source = Path(__file__).resolve().parents[1] / "scripts/imitation_ablation.py"
loader = importlib.util.spec_from_file_location("imitation_ablation", source)
assert loader and loader.loader
study = importlib.util.module_from_spec(loader)
loader.loader.exec_module(study)


def records():
    result = []
    for split in ("train", "calibration", "promotion", "test"):
        for i in range(2):
            key = f"{split}-{i}"
            result.append({"id": key, "repository": split, "task_group": key,
                "split": split, "spec": "context-route-v1", "authorized": True,
                "inputs": {"summary": "Find source " + key}, "selected": "symbol",
                "outcomes": {"symbol": {"success": i == 0, "duration_ms": 1},
                             "search": {"success": split != "train" or i == 0, "duration_ms": 2}}})
    return result


def test_identical_cohort_includes_unstable_teacher_and_preserves_heldout():
    original = records()
    before = copy.deepcopy(original)
    arms = study.arm_records(original, {"train-0": {"choice": "search", "stable": False}})
    assert original == before
    for arm in arms.values():
        assert [r["id"] for r in arm if r["split"] == "train"] == ["train-0"]
        assert "outcomes" not in arm[0]
        assert [r for r in arm if r["split"] != "train"] == [r for r in original if r["split"] != "train"]
    assert arms["outcome"][0]["selected"] == "symbol"
    assert arms["imitation"][0]["selected"] == "search"
    assert study.input_identity(arms["outcome"]) == study.input_identity(arms["imitation"])


@pytest.mark.parametrize("teacher", [
    {}, {"train-0": {"choice": "search"}, "test-0": {"choice": "search"}},
    {"train-0": {"choice": "approve"}},
])
def test_missing_heldout_or_invalid_teacher_labels_are_rejected(teacher):
    with pytest.raises(ValueError):
        study.arm_records(records(), teacher)
