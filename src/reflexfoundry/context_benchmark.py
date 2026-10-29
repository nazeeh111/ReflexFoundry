"""Executed, read-only retrieval decisions on four pinned public source trees.

Only trusted local AST/text algorithms run. Repository modules, build scripts,
commands and tests are never imported or executed. This is retrieval-stage
coverage, not autonomous coding success or independent-repository reliability.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Repository:
    name: str
    url: str
    commit: str
    package: str
    license_file: str
    split: str


REPOSITORIES = (
    Repository("toolz", "https://github.com/pytoolz/toolz", "451af60dec590a6010e2babdbf391ea8f815122f",
               "toolz", "LICENSE.txt", "train"),
    Repository("funcy", "https://github.com/Suor/funcy", "a876c7e1cf11e7c746e91fce4632ebfa93865428",
               "funcy", "LICENSE", "calibration"),
    Repository("blinker", "https://github.com/pallets-eco/blinker", "c3364059663df1ddce32799d6b1922af89a345f6",
               "src/blinker", "LICENSE.txt", "promotion"),
    Repository("cachetools", "https://github.com/tkem/cachetools", "e7104dd52bfe0e3aced6f3439fb6ed4d9c8ff52a",
               "src/cachetools", "LICENSE", "test"),
)


@dataclass(frozen=True)
class Target:
    symbol: str
    path: str
    signature: str
    contract: str


# Reviewed against the pinned public declarations/docstrings, independent of
# either retrieval implementation. No grader annotations enter the input state.
TARGETS = {
    "toolz": (
        Target("unique", "toolz/itertoolz.py", "def unique(seq, key=None):", "Return only unique elements of a sequence"),
        Target("take", "toolz/itertoolz.py", "def take(n, seq):", "The first n elements of a sequence"),
        Target("drop", "toolz/itertoolz.py", "def drop(n, seq):", "The sequence following the first n elements"),
        Target("first", "toolz/itertoolz.py", "def first(seq):", "The first element in a sequence"),
        Target("sliding_window", "toolz/itertoolz.py", "def sliding_window(n, seq):", "A sequence of overlapping subsequences"),
        Target("partition", "toolz/itertoolz.py", "def partition(n, seq, pad=no_pad):", "Partition sequence into tuples of length n"),
    ),
    "funcy": (
        Target("take", "funcy/seqs.py", "def take(n, seq):", "Returns a list of first n items in the sequence,"),
        Target("drop", "funcy/seqs.py", "def drop(n, seq):", "Skips first n items in the sequence, yields the rest."),
        Target("first", "funcy/seqs.py", "def first(seq):", "Returns the first item in the sequence."),
        Target("flatten", "funcy/seqs.py", "def flatten(seq, follow=is_seqcont):", "Flattens arbitrary nested sequence."),
        Target("distinct", "funcy/seqs.py", "def distinct(seq, key=EMPTY):", "Iterates over sequence skipping duplicates"),
        Target("partition", "funcy/seqs.py", "def partition(n, step, seq=EMPTY):", "Lazily partitions seq into parts of length n."),
    ),
    "blinker": (
        Target("Signal.connect", "src/blinker/base.py", "def connect(self, receiver: F, sender: t.Any = ANY, weak: bool = True) -> F:",
               "Connect ``receiver`` to be called when the signal is sent by"),
        Target("Signal.muted", "src/blinker/base.py", "def muted(self) -> c.Generator[None, None, None]:",
               "A context manager that temporarily disables the signal. No receivers"),
        Target("Signal.send", "src/blinker/base.py", "def send(",
               "Call all receivers that are connected to the given ``sender``"),
        Target("Signal.has_receivers_for", "src/blinker/base.py", "def has_receivers_for(self, sender: t.Any) -> bool:",
               "Check if there is at least one receiver that will be called with the"),
        Target("Signal.receivers_for", "src/blinker/base.py", "def receivers_for(",
               "Yield each receiver to be called for ``sender``, in addition to those"),
        Target("Signal.disconnect", "src/blinker/base.py", "def disconnect(self, receiver: c.Callable[..., t.Any], sender: t.Any = ANY) -> None:",
               "Disconnect ``receiver`` from being called when the signal is sent by"),
    ),
    "cachetools": (
        Target("Cache", "src/cachetools/__init__.py", "class Cache(collections.abc.MutableMapping):",
               "Mutable mapping to serve as a simple cache or cache base class."),
        Target("FIFOCache", "src/cachetools/__init__.py", "class FIFOCache(Cache):",
               "First In First Out (FIFO) cache implementation."),
        Target("LFUCache", "src/cachetools/__init__.py", "class LFUCache(Cache):",
               "Least Frequently Used (LFU) cache implementation."),
        Target("LRUCache", "src/cachetools/__init__.py", "class LRUCache(Cache):",
               "Least Recently Used (LRU) cache implementation."),
        Target("TTLCache", "src/cachetools/__init__.py", "class TTLCache(_TimedCache):",
               "LRU Cache implementation with per-item time-to-live (TTL) value."),
        Target("cached", "src/cachetools/__init__.py", "def cached(cache, key=keys.hashkey, lock=None, condition=None, info=False):",
               "Decorator to wrap a function with a memoizing callable that saves"),
    ),
}

MAX_FILES = 128
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024
SNIPPET_BYTES = 8192
_STOPWORDS = frozenset("find locate public implementation definition of the a an and to for in is with from as be source".split())


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _corpus(repo: Repository, root: Path) -> dict[str, str]:
    root = root.resolve()
    files = sorted((root / repo.package).rglob("*.py"))
    if not files or len(files) > MAX_FILES:
        raise ValueError(f"{repo.name} source count is outside the benchmark bound")
    corpus: dict[str, str] = {}
    total = 0
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("public source files must not be symlinks or escape their checkout")
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_SOURCE_BYTES:
            raise ValueError("public source exceeds the benchmark byte bound")
        corpus[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return corpus


def _snippet(path: str, lines: list[str], start: int, end: int) -> dict[str, Any]:
    text = "\n".join(lines[start:end]).encode()[:SNIPPET_BYTES].decode("utf-8", errors="ignore")
    return {"path": path, "start_line": start + 1, "text": text,
            "sha256": _hash(text.encode())}


def symbol_lookup(corpus: dict[str, str], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Cold AST lookup of an explicitly supplied qualified or simple symbol."""
    name = inputs.get("symbol")
    if not isinstance(name, str) or not name:
        return []
    hints = inputs.get("changed_files", [])
    for path in sorted(corpus, key=lambda p: (p not in hints, p)):
        source = corpus[path]
        tree = ast.parse(source)
        stack: list[tuple[ast.AST, str]] = [(tree, "")]
        while stack:
            node, prefix = stack.pop()
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + node.name
                if name == qualified or ("." not in name and name == node.name):
                    return [_snippet(path, source.splitlines(), node.lineno - 1, node.end_lineno or node.lineno)]
                prefix = qualified + "."
            stack.extend((child, prefix) for child in reversed(list(ast.iter_child_nodes(node))))
    return []


def text_search(corpus: dict[str, str], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Bounded literal/word source search: three ranked source windows, no AST."""
    summary = inputs["summary"].lower()
    words = set(re.findall(r"[a-z_][a-z_0-9]*", summary)) - _STOPWORDS
    words.update(str(inputs.get("symbol", "")).lower().split("."))
    words.discard("")
    hints = inputs.get("changed_files", [])
    hits: list[tuple[int, int, str, int]] = []
    for path in sorted(corpus):
        for index, line in enumerate(corpus[path].splitlines()):
            lowered = line.lower()
            score = len(words.intersection(re.findall(r"[a-z_][a-z_0-9]*", lowered)))
            if summary and summary in lowered:
                score += 6
            if score:
                hits.append((-score, int(path not in hints), path, index))
    result: list[dict[str, Any]] = []
    for _, _, path, index in sorted(hits):
        if any(snippet["path"] == path and abs(snippet["start_line"] - 1 - index) < 12 for snippet in result):
            continue
        lines = corpus[path].splitlines()
        result.append(_snippet(path, lines, max(0, index - 16), min(len(lines), index + 13)))
        if len(result) == 3:
            break
    return result


def grade(target: Target, snippets: list[dict[str, Any]]) -> bool:
    """Separate reviewed declaration+contract check; no retriever logic or labels."""
    return any(row["path"] == target.path and target.signature in row["text"]
               and target.contract in row["text"] for row in snippets)


def _queries(target: Target, count: int) -> list[dict[str, Any]]:
    variants = [
        {"summary": f"Locate implementation of {target.symbol}.", "changed_files": [], "symbol": target.symbol},
        {"summary": target.contract, "changed_files": [], "symbol": target.symbol},
        {"summary": target.contract, "changed_files": []},
        {"summary": target.contract.lower(), "changed_files": []},
        {"summary": f"Find public definition {target.symbol}", "changed_files": []},
        {"summary": f"Find implementation for {target.symbol}", "changed_files": [], "symbol": target.symbol},
        {"summary": f"Find public definition {target.symbol}", "changed_files": [], "symbol": target.symbol},
    ]
    return variants[:count]


def generate(output: Path, sources: dict[str, Path], repeats: int = 3) -> list[dict[str, Any]]:
    """Run fixed retrieval actions against supplied clean pinned public checkouts.

    Each repository belongs to exactly one split. Query variants are correlated
    and grouped by target. Six target groups per split cannot support broad
    deployment evidence regardless of the raw query count.
    """
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 5:
        raise ValueError("repeats must be an integer from 1 to 5")
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("context benchmark output must be a fresh directory")
    prepared = []
    for repo in REPOSITORIES:
        if repo.name not in sources:
            raise ValueError(f"missing public source checkout: {repo.name}")
        root = Path(sources[repo.name]).resolve()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True)
        if commit != repo.commit or dirty:
            raise ValueError(f"{repo.name} must be clean and pinned at {repo.commit}")
        start = time.perf_counter_ns()
        corpus = _corpus(repo, root)
        startup = (time.perf_counter_ns() - start) / 1e6
        for target in TARGETS[repo.name]:
            if target.path not in corpus or corpus[target.path].count(target.signature) != 1 or target.contract not in corpus[target.path]:
                raise ValueError(f"reviewed target contract drifted: {repo.name}/{target.symbol}")
        license_path = root / repo.license_file
        if license_path.is_symlink() or not license_path.resolve().is_relative_to(root):
            raise ValueError("license must remain in the public checkout")
        prepared.append((repo, corpus, startup, license_path.read_text()))
    output.mkdir(parents=True, exist_ok=True)
    (output / "licenses").mkdir()
    (output / "evidence").mkdir()
    records: list[dict[str, Any]] = []
    provenance = []
    for repo, corpus, startup, license_text in prepared:
        (output / "licenses" / f"{repo.name}.txt").write_text(license_text)
        provenance.append({**asdict(repo), "corpus_startup_ms": startup,
            "source_sha256": {path: _hash(text.encode()) for path, text in corpus.items()},
            "targets": [asdict(target) for target in TARGETS[repo.name]],
            "license_sha256": _hash(license_text.encode())})
        for target_index, target in enumerate(TARGETS[repo.name]):
            variants = _queries(target, 7 if repo.split == "train" else 5)
            for variant, inputs in enumerate(variants):
                inputs["summary"] = f"In {repo.name}: {inputs['summary']}"
                record_id = f"{repo.name}-{target_index:02}-{variant:02}"
                trials: dict[str, list[dict[str, Any]]] = {"symbol": [], "search": []}
                orders = []
                for trial in range(repeats):
                    order = ["symbol", "search"] if (target_index + variant + trial) % 2 else ["search", "symbol"]
                    orders.append(order)
                    for choice in order:
                        start = time.perf_counter_ns()
                        snippets = (symbol_lookup if choice == "symbol" else text_search)(corpus, inputs)
                        elapsed = (time.perf_counter_ns() - start) / 1e6
                        trials[choice].append({"duration_ms": elapsed, "success": grade(target, snippets), "snippets": snippets})
                outcomes = {choice: {"success": values[0]["success"],
                    "duration_ms": startup + statistics.median(value["duration_ms"] for value in values),
                    "median_action_ms": statistics.median(value["duration_ms"] for value in values),
                    "corpus_startup_ms": startup,
                    "trials_ms": [value["duration_ms"] for value in values]}
                    for choice, values in trials.items()}
                if any(len({value["success"] for value in values}) != 1 for values in trials.values()):
                    raise RuntimeError("retrieval outcome changed between repeated deterministic trials")
                successful = [choice for choice in outcomes if outcomes[choice]["success"]]
                selected = min(successful, key=lambda choice: outcomes[choice]["duration_ms"]) if successful else "search"
                record = {"id": record_id, "spec": "context-route-v1", "repository": repo.url,
                    "split": repo.split, "task_group": f"{repo.name}:{target.symbol}",
                    "inputs": inputs, "selected": selected, "authorized": True,
                    "outcomes": outcomes, "source": "pinned-public-source-retrieval", "oracle": {
                        "target": asdict(target), "source_sha256": _hash(corpus[target.path].encode()),
                        "evidence": f"evidence/{record_id}.json", "neither_action_succeeded": not successful}}
                records.append(record)
                (output / "evidence" / f"{record_id}.json").write_text(json.dumps({"orders": orders, "trials": trials}, indent=2) + "\n")
    from .core import validate_splits
    validate_splits(records, require_evaluation_outcomes=True)
    blob = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in records)
    (output / "records.jsonl").write_text(blob)
    manifest = {"format": 1, "benchmark": "public-source-context-retrieval-v1", "repeats": repeats,
        "records_sha256": _hash(blob.encode()), "repositories": provenance,
        "counts": {repo.split: sum(row["split"] == repo.split for row in records) for repo in REPOSITORIES},
        "bounds": {"source_files": MAX_FILES, "source_bytes": MAX_SOURCE_BYTES, "file_bytes": MAX_FILE_BYTES,
                   "snippet_bytes": SNIPPET_BYTES, "search_snippets": 3},
        "timing": "Retrospective per-request sum of measured source read startup plus median in-memory retrieval wall time across alternating paired trials. Each action is charged the same repository startup on every modeled request. Raw trials and median_action_ms remain retrieval-only. No native CLI, grader, repository preparation, or autonomous-agent elapsed time is claimed; model overhead is added separately by evaluation.",
        "independence": "One actual repository per split, six target groups with correlated query variants each. Raw query counts do not create independent promotion evidence.",
        "scope": "Read-only source retrieval stage; no repository code executes. Public declaration/docstring coverage is not coding-task completion, semantic context sufficiency, or evidence of broad reliability.",
        "deployment_allowed": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return records
