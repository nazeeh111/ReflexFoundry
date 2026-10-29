"""Two public repair fixtures and local preflight; never invokes an agent.

Only clean, explicitly supplied pinned source is copied. Independent grader
files live outside the candidate checkout. Source imports are pinned to that
checkout even for packages using a ``src`` layout.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Task:
    name: str
    repository_name: str
    repository: str
    commit: str
    package: str
    source_file: str
    license_file: str
    focused_args: tuple[str, ...]
    full_args: tuple[str, ...]
    mutation_before: str
    mutation_after: str
    repair_contract: str
    symbol: str
    grader: str

    @property
    def import_root(self) -> str:
        return str(Path(self.package).parent)

    @property
    def context_inputs(self) -> dict[str, Any]:
        return {"summary": f"In {self.repository_name}: Locate implementation of {self.symbol}.",
                "changed_files": [], "symbol": self.symbol}

    @property
    def request(self) -> dict[str, Any]:
        return {"spec": "context-route-v1", "inputs": self.context_inputs}


TASKS = (
    Task(
        name="funcy-first", repository_name="funcy", repository="https://github.com/Suor/funcy",
        commit="a876c7e1cf11e7c746e91fce4632ebfa93865428", package="funcy",
        source_file="funcy/seqs.py", license_file="LICENSE",
        focused_args=("-m", "pytest", "-q", "-W", "error", "tests/test_seqs.py::test_first"),
        full_args=("-m", "pytest", "-q", "-W", "error"),
        mutation_before="return next(iter(seq), None)",
        mutation_after="return next(islice(seq, 1, None), None)",
        repair_contract=(
            "Repair first(seq) in funcy/seqs.py. It must return the first element of a sequence or iterator, "
            "consume only that first iterator item, preserve falsey elements, and return None for empty input. "
            "Make the smallest correct source repair without editing tests or unrelated files."
        ),
        symbol="first",
        grader='''from pathlib import Path
import funcy
assert Path(funcy.__file__).resolve().is_relative_to(Path.cwd().resolve())
from funcy import first
assert first("xyz") == "x"
assert first([]) is None
assert first([None, 2]) is None
assert first([0, 1]) == 0
assert first([False, True]) is False
source = iter([7, 8, 9])
assert first(source) == 7
assert next(source) == 8
assert first(iter(())) is None
source = (value for value in range(3))
assert first(source) == 0
assert next(source) == 1
print("independent Funcy first contract passed")
''',
    ),
    Task(
        name="cachetools-getitem", repository_name="cachetools", repository="https://github.com/tkem/cachetools",
        commit="e7104dd52bfe0e3aced6f3439fb6ed4d9c8ff52a", package="src/cachetools",
        source_file="src/cachetools/__init__.py", license_file="LICENSE",
        focused_args=("-m", "pytest", "-q", "tests/test_cache.py::CacheTest::test_update"),
        full_args=("-m", "pytest", "-q"),
        mutation_before="            return self.__data[key]",
        mutation_after="            return key if key in self.__data else self.__data[key]",
        repair_contract=(
            "Repair Cache.__getitem__ in src/cachetools/__init__.py. A present key must return its stored value, "
            "including None and other falsey values. A missing key must continue through __missing__, raising "
            "KeyError by default and respecting subclass implementations. Reads must not change cache size. "
            "Make the smallest correct source repair without editing tests or unrelated files."
        ),
        symbol="Cache.__getitem__",
        grader='''from pathlib import Path
import cachetools
assert Path(cachetools.__file__).resolve().is_relative_to(Path.cwd().resolve())
from cachetools import Cache
cache = Cache(maxsize=4)
cache["different"] = 17
cache["none"] = None
cache["zero"] = 0
cache["false"] = False
before = (len(cache), cache.currsize)
assert cache["different"] == 17
assert cache["none"] is None
assert cache["zero"] == 0
assert cache["false"] is False
assert (len(cache), cache.currsize) == before
try:
    cache["absent"]
except KeyError as error:
    assert error.args == ("absent",)
else:
    raise AssertionError("missing default cache key must raise KeyError")
class Missing(Cache):
    def __missing__(self, key):
        calls.append(key)
        return ("fallback", key)
calls = []
custom = Missing(maxsize=2)
custom["stored"] = 23
assert custom["stored"] == 23
assert calls == []
before = (len(custom), custom.currsize)
assert custom["absent"] == ("fallback", "absent")
assert calls == ["absent"]
assert (len(custom), custom.currsize) == before
print("independent cachetools getitem contract passed")
''',
    ),
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mutate_source(task: Task, source: str) -> str:
    if source.count(task.mutation_before) != 1:
        raise ValueError(f"mutation anchor is not unique: {task.name}")
    return source.replace(task.mutation_before, task.mutation_after, 1)


def source_inventory(task: Task, source: Path) -> dict[str, str]:
    """Validate the pin and inventory tracked file contents, not Git state.

    Internal source-file links are allowed; copying materializes their public
    contents as regular files. External links and non-file entries are refused.
    """
    source = source.resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=source, text=True
    )
    if commit != task.commit or status:
        raise ValueError(f"{task.repository_name} must be clean and pinned at {task.commit}")
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).decode().split("\0")
    names = [name for name in names if name]
    if len(names) > 1024:
        raise ValueError("public source exceeds the 1024-file bound")
    inventory: dict[str, str] = {}
    size = 0
    for name in names:
        path = source / name
        if not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError("public source files must remain within their checkout")
        data = path.read_bytes()
        size += len(data)
        if len(data) > 2 * 1024 * 1024 or size > 16 * 1024 * 1024:
            raise ValueError("public source exceeds the byte bound")
        inventory[name] = sha(data)
    for name in (task.source_file, task.license_file):
        if name not in inventory:
            raise ValueError(f"required tracked source is missing: {name}")
    return inventory


def copy_source(task: Task, source: Path, destination: Path) -> dict[str, str]:
    inventory = source_inventory(task, source)
    destination.mkdir(parents=True, exist_ok=False)
    for name, expected in inventory.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
        if sha(target.read_bytes()) != expected:
            raise ValueError("public source changed while being copied")
    return inventory


def run_check(task: Task, root: Path, args: tuple[str, ...], *, timeout: int = 90) -> dict[str, Any]:
    """Execute a declared local check, importing from this candidate checkout."""
    env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR", "SYSTEMROOT") if key in os.environ}
    env.update(PYTHONPATH=str((root / task.import_root).resolve()),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    start = time.perf_counter_ns()
    # -B prevents writes but still permits loading existing bytecode. Point
    # imports at a fresh observer-owned cache so candidate .pyc files cannot
    # replace the inspected source during independent checks.
    with tempfile.TemporaryDirectory(prefix="reflex-native-check-cache-") as cache:
        env["PYTHONPYCACHEPREFIX"] = cache
        try:
            result = subprocess.run([sys.executable, "-B", *args], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=timeout, check=False)
            code, output, timed_out = result.returncode, result.stdout + result.stderr, False
        except subprocess.TimeoutExpired as error:
            code, timed_out = None, True
            output = "local check exceeded its declared timeout"
            if error.stdout:
                output += "\n" + (error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout)
    output = output.replace(str(root), "<repository>").replace(sys.prefix, "<python-environment>")
    return {"passed": code == 0 and not timed_out, "exit_code": code, "timed_out": timed_out,
            "wall_ms": (time.perf_counter_ns() - start) / 1e6, "output": output[-12000:]}


def preflight(task: Task, source: Path, output: Path) -> dict[str, Any]:
    """Check clean/full and mutant/focused outcomes without starting Codex."""
    if output.exists():
        raise FileExistsError("preflight evidence needs a fresh file")
    with tempfile.TemporaryDirectory(prefix="reflex-native-v2-preflight-") as temp:
        parent = Path(temp)
        root = parent / task.repository_name
        inventory = copy_source(task, source, root)
        grader = parent / "independent-grader.py"
        grader.write_text(task.grader)
        checks = {"clean_full": run_check(task, root, task.full_args),
                  "clean_focused": run_check(task, root, task.focused_args),
                  "clean_grader": run_check(task, root, (str(grader),))}
        target = root / task.source_file
        original = target.read_bytes()
        mutated = mutate_source(task, original.decode()).encode()
        target.write_bytes(mutated)
        checks.update(mutant_focused=run_check(task, root, task.focused_args),
                      mutant_grader=run_check(task, root, (str(grader),)))
        changed = [name for name, expected in inventory.items() if sha((root / name).read_bytes()) != expected]
        expected = (all(checks[key]["passed"] for key in ("clean_full", "clean_focused", "clean_grader"))
                    and all(checks[key]["exit_code"] == 1 for key in ("mutant_focused", "mutant_grader"))
                    and changed == [task.source_file])
        license_bytes = (source / task.license_file).read_bytes()
        value = {"task": task.name, "repository": task.repository, "commit": task.commit,
                 "source_files": inventory, "source_sha256": sha(original), "mutated_sha256": sha(mutated),
                 "materialized_public_links": {name: os.readlink(source / name) for name in inventory
                                               if (source / name).is_symlink()},
                 "grader_sha256": sha(task.grader.encode()), "request": task.request,
                 "license": {"file": task.license_file, "sha256": sha(license_bytes),
                             "text": license_bytes.decode()},
                 "checks": checks, "changed_public_files": changed, "preflight_passed": expected,
                 "codex_invocations": 0,
                 "scope": "Local preparation only; no agent task result or model-performance claim."}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    if not expected:
        raise RuntimeError(f"local task preflight failed: {task.name}; inspect {output}")
    return value
