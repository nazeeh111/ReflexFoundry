"""Executed, self-contained coding validation workloads.

These are generated repositories, not claims about SWE-bench or autonomous
agent problem solving.  The decision is which checks to run on an existing
candidate patch.  A separate public-contract grader determines whether an
accept/reject result was correct.  Nothing from that grader enters inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_TASKS = {"train": 160, "calibration": 60, "promotion": 60, "test": 80}
SPLIT_SEEDS = {"train": 101, "calibration": 307, "promotion": 509, "test": 701}


def _run(root: Path, args: list[str], *, timeout: float = 15) -> dict[str, Any]:
    start = time.perf_counter_ns()
    result = subprocess.run(
        [sys.executable, "-B", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    elapsed = (time.perf_counter_ns() - start) / 1e6
    if result.returncode not in (0, 1):
        raise RuntimeError(f"fixture execution failed: {result.stderr[-1500:]}")
    # Only deliberately failing contract assertions are normal benchmark outcomes.
    if result.returncode and "AssertionError" not in result.stderr:
        raise RuntimeError(f"invalid fixture, not a rejected patch: {result.stderr[-1500:]}")
    return {"passed": result.returncode == 0, "duration_ms": elapsed}


def _write_fixture(root: Path, *, number: int, variant: str, bad: bool) -> dict[str, str]:
    """Write originals, then the candidate patch. Return reproducibility hashes."""
    factor = 2 + number % 7
    prefix = f"item-{number}"
    # A small package with shared arithmetic and two distinct consumers.
    original = {
        "units.py": (
            f"FACTOR = {factor}\n"
            "def convert(value):\n    return value * FACTOR\n"
            "def scale():\n    return FACTOR\n"
        ),
        "labels.py": (
            "from units import convert\n"
            f"PREFIX = {prefix!r}\n"
            "def label(value):\n    return PREFIX + ':' + str(convert(value))\n"
            "def display(value):\n    return str(value)\n"
        ),
        "invoice.py": (
            "from units import convert\n"
            "def total(values):\n    return sum(convert(v) for v in values)\n"
            "def discount(value):\n    return convert(value) // 2\n"
        ),
    }
    for name, code in original.items():
        (root / name).write_text(code, encoding="utf-8")
    before = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
    if variant == "local":
        # Requested fix: display must add its stable prefix. Some patches have a typo.
        patched = original["labels.py"].replace(
            "return str(value)",
            "return PREFIX + ':' + str(value)" if not bad else "return PREFIX + '-' + str(value)",
        )
        changed = "labels.py"
    else:
        # Requested fix: accept numeric strings as well as integers. Some candidate
        # patches accidentally change integer conversion, which breaks consumers.
        body = "return int(value) * FACTOR" if not bad else "return (int(value) + 1) * FACTOR"
        patched = original["units.py"].replace("return value * FACTOR", body)
        changed = "units.py"
    (root / changed).write_text(patched, encoding="utf-8")
    # The focused check tests the narrow requested behavior. It does not claim
    # to replace shared-consumer coverage.
    focused = (
        "import unittest\nfrom labels import display\n"
        f"class Focus(unittest.TestCase):\n    def test_display(self):\n        self.assertEqual(display(7), {prefix + ':7'!r})\n"
        if variant == "local"
        else "import unittest\nfrom units import convert\n"
        "class Focus(unittest.TestCase):\n    def test_numeric_string(self):\n        self.assertIsInstance(convert('7'), int)\n"
    )
    (root / "test_focus.py").write_text(focused, encoding="utf-8")
    # A meaningful full suite exercises arithmetic consumer invariants over a
    # grid of values, rather than adding artificial latency or sleeps.
    full = f"""import unittest
from labels import label
from invoice import total, discount
class Consumers(unittest.TestCase):
    def test_invoice_grid(self):
        for n in range(-4000, 4001):
            self.assertEqual(total([n, n + 1, 2]), (2 * n + 3) * {factor})
            self.assertEqual(discount(n), (n * {factor}) // 2)
    def test_labels(self):
        for n in range(-200, 201):
            self.assertEqual(label(n), {prefix!r} + ':' + str(n * {factor}))
"""
    (root / "test_consumers.py").write_text(full, encoding="utf-8")
    # The independent grader uses known public contracts directly and never
    # imports unittest or the candidate check files. It checks all three modules.
    oracle = f"""from units import convert
from labels import label, display
from invoice import total, discount
for value in (-19, -1, 0, 1, 7, 23, 101):
    assert convert(value) == value * {factor}
    assert label(value) == {prefix!r} + ':' + str(value * {factor})
    assert total([value, 3, -1]) == (value + 2) * {factor}
    assert discount(value) == (value * {factor}) // 2
"""
    if variant == "local":
        oracle += f"assert display(7) == {prefix + ':7'!r}\n"
    else:
        oracle += f"assert convert('7') == 7 * {factor}\n"
    (root / "oracle.py").write_text(oracle, encoding="utf-8")
    after = hashlib.sha256(patched.encode()).hexdigest()
    return {"original_sha256": before, "patch_sha256": after, "changed": changed}


def _task(root: Path, split: str, index: int, seed: int, repeats: int) -> dict[str, Any]:
    rng = random.Random(seed * 100003 + index)
    variant = "shared" if index % 2 else "local"
    # Both correct and incorrect patches occur in each task class. Shared risk
    # is informative but does not reveal whether an individual patch is correct.
    bad = rng.random() < (0.8 if variant == "shared" else 0.25)
    number = seed * 1000 + index
    hashes = _write_fixture(root, number=number, variant=variant, bad=bad)
    # Alternate measurement order so one candidate does not always receive the
    # filesystem cache advantage. An independent third run supplies the oracle.
    commands = {
        "focused": ["-m", "unittest", "-q", "test_focus"],
        "full": ["-m", "unittest", "discover", "-q", "-p", "test_*.py"],
    }
    trials: dict[str, list[dict[str, Any]]] = {"focused": [], "full": []}
    orders = []
    for trial in range(repeats):
        order = ["focused", "full"] if (index + trial) % 2 else ["full", "focused"]
        orders.append(order)
        for choice in order:
            trials[choice].append(_run(root, commands[choice]))
    measured = {
        choice: {
            "passed": values[0]["passed"],
            "duration_ms": statistics.median(row["duration_ms"] for row in values),
            "trials_ms": [row["duration_ms"] for row in values],
        }
        for choice, values in trials.items()
    }
    if any(len({row["passed"] for row in values}) != 1 for values in trials.values()):
        raise RuntimeError("flaky validation result across repeated trials")
    oracle = _run(root, ["oracle.py"])
    outcomes = {
        key: {
            "success": value["passed"] == oracle["passed"],
            "duration_ms": value["duration_ms"],
            "trials_ms": value["trials_ms"],
            "checks_passed": value["passed"],
            "false_acceptance": value["passed"] and not oracle["passed"],
        }
        for key, value in measured.items()
    }
    valid = [choice for choice in commands if outcomes[choice]["success"]]
    if not valid:
        raise RuntimeError("independent oracle disagreed with every validation action")
    fastest = min(valid, key=lambda choice: outcomes[choice]["duration_ms"])
    # Full suite is chosen on near ties, which prevents claiming jitter savings.
    if "full" in valid and outcomes["full"]["duration_ms"] <= outcomes[fastest]["duration_ms"] * 1.03:
        fastest = "full"
    summaries = (
        [
            "Add a stable item prefix to the display formatter; arithmetic contracts are unchanged.",
            "Fix the display string prefix in the labels module only.",
            "Update presentation formatting without changing shared numeric conversion.",
            "Correct the display formatter to include the existing item identifier.",
        ]
        if variant == "local"
        else [
            "Accept numeric strings in shared conversion used by invoices and item labels.",
            "Update the shared numeric converter, preserving existing consumer contracts.",
            "Extend arithmetic input handling in the conversion module used across the package.",
            "Fix numeric-string conversion in the shared units helper and keep consumer results stable.",
        ]
    )
    return {
        "id": f"{split}-{index:04d}",
        "repository": f"fixture-{split}-{index // 10:03d}",
        "split": split,
        "spec": "test-scope-v1",
        "inputs": {
            "summary": summaries[(index // 2) % len(summaries)] + f" Item identifier: item-{number}.",
            "changed_files": [hashes.pop("changed")],
        },
        "selected": fastest,
        "outcomes": outcomes,
        "baseline_ms": outcomes["full"]["duration_ms"],
        "authorized": True,
        "source": "executed-fixture",
        "oracle": {
            **oracle,
            "grader": "public-contract-v1",
            "interpretation": "correct candidate-patch acceptance or rejection",
        },
        "provenance": {
            **hashes,
            "seed": seed,
            "index": index,
            "variant": variant,
            "measurement_orders": orders,
            "repeats": repeats,
            "python": sys.version.split()[0],
            "generated_repository": True,
        },
    }


def generate(
    output: Path,
    tasks_per_split: dict[str, int] | None = None,
    repeats: int = 3,
) -> list[dict[str, Any]]:
    """Run fresh repositories and save records.jsonl plus a provenance manifest.

    ``output`` is a directory. Source fixtures are reacquirable from this code;
    hashes, task seeds and actual measured outcomes are retained in records.
    Existing outputs are rejected to prevent mixing old and fresh experiments.
    """
    counts = DEFAULT_TASKS if tasks_per_split is None else tasks_per_split
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 20:
        raise ValueError("repeats must be an integer from 1 to 20")
    if not counts or any(k not in SPLIT_SEEDS for k in counts):
        raise ValueError("splits must be train, calibration, promotion, or test")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 10000 for v in counts.values()):
        raise ValueError("split counts must be integers from 0 to 10000")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"benchmark output must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    start = time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix="reflexfoundry-fixtures-") as temp:
        for split, count in counts.items():
            for index in range(count):
                root = Path(temp) / f"{split}-{index:04d}"
                root.mkdir()
                record = _task(root, split, index, SPLIT_SEEDS[split], repeats)
                records.append(record)
    blob = "".join(json.dumps(row, sort_keys=True) + "\n" for row in records)
    (output / "records.jsonl").write_text(blob, encoding="utf-8")
    manifest = {
        "benchmark": "candidate-patch-validation-v1",
        "counts": counts,
        "repeats": repeats,
        "time_aggregation": "median per candidate across paired, alternating-order trials",
        "records_sha256": hashlib.sha256(blob.encode()).hexdigest(),
        "elapsed_ms": (time.perf_counter_ns() - start) / 1e6,
        "split_seeds": {key: SPLIT_SEEDS[key] for key in counts},
        "limits": [
            "Generated Python repositories share a small fixture grammar; this is not real-world repository generalization.",
            "Measures validation decision outcomes for supplied patches, not autonomous coding-task completion.",
            "Subprocess wall time varies across hosts and loads. No LLM latency or monetary savings are inferred.",
            "No sleeps, simulated timing, private transcripts, hosted APIs, or teacher labels are used.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return records


def heuristic(inputs: dict[str, Any]) -> str:
    """Conservative transparent baseline: shared conversion requires all checks."""
    files = inputs.get("changed_files", [])
    return "full" if any(Path(str(path)).name == "units.py" for path in files) else "focused"


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Small executed-evidence summary for CLI callers."""
    result: dict[str, Any] = {"n": len(records), "policies": []}
    for name, selector in (
        ("no-delegation", lambda row: "full"),
        ("deterministic-heuristic", lambda row: heuristic(row["inputs"])),
        ("always-focused", lambda row: "focused"),
    ):
        chosen = [row["outcomes"][selector(row)] for row in records]
        result["policies"].append({
            "name": name,
            "n": len(chosen),
            "success_rate": sum(bool(row["success"]) for row in chosen) / max(1, len(chosen)),
            "mean_ms": math.fsum(float(row["duration_ms"]) for row in chosen) / max(1, len(chosen)),
            "false_acceptances": sum(bool(row["false_acceptance"]) for row in chosen),
        })
    return result
