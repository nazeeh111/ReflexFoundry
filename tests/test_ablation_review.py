"""Independent fixed-input checks; never load a policy or run a fit."""
import importlib.util
from collections import Counter
from pathlib import Path

import pytest

from reflexfoundry.core import read_records
from reflexfoundry.model import training_examples

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location("reviewed_ablation", ROOT / "scripts/imitation_ablation.py")
assert loader and loader.loader
study = importlib.util.module_from_spec(loader)
loader.loader.exec_module(study)


def fixed_records():
    return read_records(ROOT / "benchmarks/context-v1/scoped-v1/records.jsonl")


def test_fixed_corpus_and_strict_fastest_successful_targets():
    records = fixed_records()
    assert Counter((r["split"], r["repository"]) for r in records) == {
        ("train", "https://github.com/pytoolz/toolz"): 42,
        ("calibration", "https://github.com/Suor/funcy"): 30,
        ("promotion", "https://github.com/pallets-eco/blinker"): 30,
        ("test", "https://github.com/tkem/cachetools"): 30,
    }
    eligible = study.eligible_training(records)
    assert len(eligible) == 36
    for row in eligible:
        target = training_examples([row])[0][0]["expected"]["decision"]
        safe = {key: value for key, value in row["outcomes"].items() if value["success"]}
        assert row["outcomes"][target]["success"]
        assert row["outcomes"][target]["duration_ms"] == min(o["duration_ms"] for o in safe.values())


def test_every_teacher_disagreement_and_instability_is_retained():
    records = fixed_records()
    eligible = study.eligible_training(records)
    teacher = {}
    for row in eligible:
        label = training_examples([row])[0][0]["expected"]["decision"]
        teacher[row["id"]] = {"choice": "search" if label == "symbol" else "symbol", "stable": False}
    arms = study.arm_records(records, teacher)
    for arm, rows in arms.items():
        training = [r for r in rows if r["split"] == "train"]
        assert [r["id"] for r in training] == [r["id"] for r in eligible]
        assert all("outcomes" not in r for r in training)
        assert [r for r in rows if r["split"] != "train"] == [r for r in records if r["split"] != "train"]
        examples, _ = training_examples(training)
        assert len(examples) == 36
        if arm == "imitation":
            assert [e["expected"]["decision"] for e in examples] == [teacher[r["id"]]["choice"] for r in eligible]
    left, right = (arms[a] for a in study.ARMS)
    assert study.input_identity(left) == study.input_identity(right)
    assert all(a["selected"] != b["selected"] for a, b in zip(left, right) if a["split"] == "train")


def test_native_split_has_same_row_identity_before_and_after_serialization():
    split_calibration = pytest.importorskip("laya.train").split_calibration

    eligible = study.eligible_training(fixed_records())
    examples, _ = training_examples(eligible)
    args = (400, study.RECIPE["calib_frac"], study.RECIPE["calib_seed"])
    original = split_calibration(eligible, *args)
    encoded = split_calibration(examples, *args)
    assert [len(part) for part in original] == [31, 5]
    for raw, prepared in zip(original, encoded):
        assert [r["inputs"] for r in raw] == [r["state"] for r in prepared]
