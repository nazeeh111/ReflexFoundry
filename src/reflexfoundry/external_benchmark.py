"""Six mutation-based holdout smoke tasks on two pinned public repositories.

This evaluates candidate-patch validation, not autonomous agent task solving.
Repository suites and an independently written public-contract grader execute
for every task. Source checkouts must be supplied explicitly; this module
neither fetches code nor installs dependencies during a benchmark run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Repository:
    name: str
    url: str
    commit: str
    source_file: str
    license_file: str
    test_file: str
    full_args: tuple[str, ...]
    oracle: str


REPOSITORIES = (
    Repository(
        "toolz",
        "https://github.com/pytoolz/toolz",
        "451af60dec590a6010e2babdbf391ea8f815122f",
        "toolz/itertoolz.py",
        "LICENSE.txt",
        "toolz/tests/test_itertoolz.py",
        ("-m", "pytest", "-q"),
        "from toolz import first, take, drop, sliding_window\n"
        "assert first('xyz') == 'x'\n"
        "assert list(take(3, iter(range(8)))) == [0, 1, 2]\n"
        "assert list(take(0, iter(range(8)))) == []\n"
        "assert list(drop(1, iter(range(4)))) == [1, 2, 3]\n"
        "assert list(sliding_window(3, range(5))) == [(0, 1, 2), (1, 2, 3), (2, 3, 4)]\n",
    ),
    Repository(
        "funcy",
        "https://github.com/Suor/funcy",
        "a876c7e1cf11e7c746e91fce4632ebfa93865428",
        "funcy/seqs.py",
        "LICENSE",
        "tests/test_seqs.py",
        ("-m", "pytest", "-q", "-W", "error"),
        "from funcy import first, second, take, drop, rest\n"
        "assert first('xyz') == 'x'\n"
        "assert first([]) is None\n"
        "assert second('xyz') == 'y'\n"
        "assert take(3, iter(range(8))) == [0, 1, 2]\n"
        "assert take(0, iter(range(8))) == []\n"
        "assert list(drop(1, iter(range(4)))) == [1, 2, 3]\n"
        "assert list(rest([4, 5, 6])) == [5, 6]\n",
    ),
)


@dataclass(frozen=True)
class Mutation:
    id: str
    function: str
    before: str
    after: str
    summary: str
    expected_valid: bool
    expected_focused_pass: bool


def mutations(name: str) -> tuple[Mutation, ...]:
    if name == "toolz":
        return (
            Mutation(
                "take-refactor", "take",
                "return itertools.islice(seq, n)",
                "return itertools.islice(iter(seq), n)",
                "Make the iterator conversion explicit in take while preserving lazy sequence behavior.",
                True, True,
            ),
            Mutation(
                "first-refactor", "first",
                "return next(iter(seq))",
                "return next(itertools.islice(seq, 1, None))",
                "Refactor first element retrieval in the public sequence utility.",
                False, False,
            ),
            Mutation(
                "take-shared-iterator", "take",
                "return itertools.islice(seq, n)",
                "return itertools.islice(seq, n if hasattr(seq, '__len__') else max(0, n - 1))",
                "Adjust iterator handling in take, a shared helper used by windowing consumers.",
                False, True,
            ),
        )
    if name == "funcy":
        return (
            Mutation(
                "take-refactor", "take",
                "return list(islice(seq, n))",
                "return [item for item in islice(seq, n)]",
                "Refactor construction of the list returned by take while preserving sequence order.",
                True, True,
            ),
            Mutation(
                "first-refactor", "first",
                "return next(iter(seq), None)",
                "return next(islice(seq, 1, None), None)",
                "Refactor first element retrieval while keeping its public empty-sequence contract.",
                False, False,
            ),
            Mutation(
                "drop-shared-iterator", "drop",
                "return islice(seq, n, None)",
                "return islice(seq, n + int(n == 1), None)",
                "Adjust offset handling in drop, the shared iterator helper used by rest and second.",
                False, True,
            ),
        )
    raise ValueError(f"unknown repository: {name}")


def apply_mutation(source: str, mutation: Mutation) -> str:
    """Require one exact reviewed edit; fail instead of applying to drifted code."""
    if source.count(mutation.before) != 1:
        raise ValueError(f"mutation anchor is not unique: {mutation.id}")
    return source.replace(mutation.before, mutation.after, 1)


def _run(root: Path, args: tuple[str, ...], *, timeout: int = 90) -> dict[str, Any]:
    env = dict(os.environ)
    # Import candidate sources from cwd, without private caller import paths or
    # unrelated third-party pytest plugins changing collection or timing.
    env.pop("PYTHONPATH", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    start = time.perf_counter_ns()
    result = subprocess.run(
        [sys.executable, "-B", *args], cwd=root, env=env,
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    elapsed = (time.perf_counter_ns() - start) / 1e6
    if result.returncode not in (0, 1):
        raise RuntimeError(f"repository command failed to execute: {result.stderr[-1000:]}")
    output = (result.stdout + result.stderr).replace(str(root), "<repository>")
    output = output.replace(sys.prefix, "<python-environment>")
    return {
        "passed": result.returncode == 0,
        "duration_ms": elapsed,
        "exit_code": result.returncode,
        "output": output[-8000:],
    }


def _outcomes(trials: dict[str, list[dict[str, Any]]], oracle_passed: bool) -> dict[str, Any]:
    outcomes = {}
    for choice, values in trials.items():
        if len({row["passed"] for row in values}) != 1:
            raise RuntimeError(f"flaky {choice} result across trials")
        passed = values[0]["passed"]
        outcomes[choice] = {
            "success": passed == oracle_passed,
            "duration_ms": statistics.median(row["duration_ms"] for row in values),
            "trials_ms": [row["duration_ms"] for row in values],
            "checks_passed": passed,
            "false_acceptance": passed and not oracle_passed,
        }
    return outcomes


def generate(output: Path, sources: dict[str, Path], *, repeats: int = 2) -> list[dict[str, Any]]:
    """Execute pinned sources in disposable copies; save complete smoke evidence.

    Preparation: install pytest and whatever==0.7; install the pinned Toolz
    package normally so its official version-metadata check can find metadata.
    ``sources`` maps ``toolz`` and ``funcy`` to the pinned clean git checkouts.
    The source checkouts are inspected and copied, never mutated.
    """
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 5:
        raise ValueError("repeats must be an integer from 1 to 5")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output must be a fresh directory: {output}")
    for repo in REPOSITORIES:
        source = Path(sources[repo.name])
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        if commit != repo.commit:
            raise ValueError(f"{repo.name} must be pinned at {repo.commit}")
        status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True)
        if status:
            raise ValueError(f"{repo.name} source has tracked changes")
    output.mkdir(parents=True, exist_ok=True)
    (output / "licenses").mkdir()
    (output / "logs").mkdir()
    records: list[dict[str, Any]] = []
    baselines = []
    with tempfile.TemporaryDirectory(prefix="reflexfoundry-public-") as temp:
        for repo in REPOSITORIES:
            source = Path(sources[repo.name])
            (output / "licenses" / f"{repo.name}.txt").write_text(
                (source / repo.license_file).read_text(), encoding="utf-8",
            )
            original = Path(temp) / f"{repo.name}-original"
            shutil.copytree(source, original, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
            (original / "reflex_oracle.py").write_text(repo.oracle, encoding="utf-8")
            baseline = _run(original, repo.full_args)
            baseline_oracle = _run(original, ("reflex_oracle.py",))
            if not baseline["passed"] or not baseline_oracle["passed"]:
                raise RuntimeError(f"{repo.name} original failed baseline: {baseline['output']} {baseline_oracle['output']}")
            baselines.append({"repository": repo.name, "suite": baseline, "oracle": baseline_oracle})
            for index, mutation in enumerate(mutations(repo.name)):
                root = Path(temp) / f"{repo.name}-{mutation.id}"
                shutil.copytree(original, root)
                path = root / repo.source_file
                original_bytes = path.read_bytes()
                path.write_text(apply_mutation(original_bytes.decode(), mutation), encoding="utf-8")
                focused_args = ("-m", "pytest", "-q", f"{repo.test_file}::test_{mutation.function}")
                trials: dict[str, list[dict[str, Any]]] = {"focused": [], "full": []}
                orders = []
                for repeat in range(repeats):
                    order = ["focused", "full"] if (index + repeat) % 2 else ["full", "focused"]
                    orders.append(order)
                    for choice in order:
                        trials[choice].append(_run(root, focused_args if choice == "focused" else repo.full_args))
                oracle = _run(root, ("reflex_oracle.py",))
                outcomes = _outcomes(trials, oracle["passed"])
                if oracle["passed"] != mutation.expected_valid:
                    raise RuntimeError(f"unexpected independent grader result: {repo.name}/{mutation.id}")
                if trials["focused"][0]["passed"] != mutation.expected_focused_pass:
                    raise RuntimeError(f"unexpected focused result: {repo.name}/{mutation.id}")
                if not outcomes["full"]["success"]:
                    raise RuntimeError(f"official full suite disagrees with public-contract oracle: {repo.name}/{mutation.id}")
                valid = [choice for choice in outcomes if outcomes[choice]["success"]]
                selected = min(valid, key=lambda choice: outcomes[choice]["duration_ms"])
                record = {
                    "id": f"public-{repo.name}-{mutation.id}",
                    "repository": repo.name,
                    "task_group": f"{repo.name}-{mutation.function}",
                    "split": "test",
                    "spec": "test-scope-v1",
                    "inputs": {"summary": mutation.summary, "changed_files": [repo.source_file]},
                    "selected": selected,
                    "outcomes": outcomes,
                    "baseline_ms": outcomes["full"]["duration_ms"],
                    "authorized": True,
                    "source": "public-repository-mutation",
                    "oracle": {k: v for k, v in oracle.items() if k != "output"},
                    "provenance": {
                        "url": repo.url, "commit": repo.commit, "license": "BSD-3-Clause",
                        "mutation": {"id": mutation.id, "before": mutation.before, "after": mutation.after},
                        "original_sha256": hashlib.sha256(original_bytes).hexdigest(),
                        "candidate_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "oracle_source_sha256": hashlib.sha256(repo.oracle.encode()).hexdigest(),
                        "commands": {
                            "focused": ["{python}", "-B", *focused_args],
                            "full": ["{python}", "-B", *repo.full_args],
                            "oracle": ["{python}", "-B", "reflex_oracle.py"],
                        },
                        "repeats": repeats, "measurement_orders": orders,
                    },
                }
                records.append(record)
                (output / "logs" / f"{record['id']}.json").write_text(
                    json.dumps({"trials": trials, "oracle": oracle}, indent=2) + "\n", encoding="utf-8",
                )
    blob = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    (output / "records.jsonl").write_text(blob, encoding="utf-8")
    manifest = {
        "benchmark": "public-repository-mutation-smoke-v1", "n": len(records),
        "repositories": [{"name": r.name, "url": r.url, "commit": r.commit, "license": "BSD-3-Clause"} for r in REPOSITORIES],
        "records_sha256": hashlib.sha256(blob.encode()).hexdigest(),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "repeats": repeats, "timing": "median subprocess wall time, alternating order",
        "pytest_plugin_autoload": False, "original_baselines": baselines,
        "limits": [
            "Six hand-authored mutations on two public repositories are a holdout smoke test, not a statistically powered study.",
            "The decision validates supplied candidate patches; it does not measure autonomous agent coding-task success.",
            "The independently authored public-contract grader covers the selected APIs, not every possible repository contract.",
            "Focused commands deliberately run the official changed-function test; shared-consumer coverage can be missed.",
            "Official full suite commands are used unchanged; documented upstream platform skips remain visible in logs.",
            "No LLM decisions, latency, token costs, monetary savings, or model improvements are inferred by this runner.",
            "Host load, filesystem caches, and subprocess startup contribute to measured timing. No artificial sleeps are added.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True, help="parent containing pinned toolz/ and funcy/ checkouts")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    rows = generate(args.output, {repo.name: args.sources / repo.name for repo in REPOSITORIES}, repeats=args.repeats)
    print(json.dumps({"n": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
