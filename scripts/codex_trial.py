"""Bounded paired Codex coding trial; never stores event transcripts.

Run with the project's existing test/runtime Python. --prepare-only performs no
Codex invocation; --run-index selects exactly one of four predeclared runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from reflexfoundry.external_benchmark import REPOSITORIES, apply_mutation, mutations  # noqa: E402
from reflexfoundry.lifecycle import transition  # noqa: E402

SOURCE = Path("/private/tmp/reflexfoundry-research/toolz")
OUTPUT = PROJECT / "benchmarks/codex-e2e-v1"
ORDER = [(1, "original"), (1, "shadow"), (2, "shadow"), (2, "original")]
ALLOWED = {"pytest", "python", "python3", "rg", "git", "npm", "cargo", "go"}
REPO = REPOSITORIES[0]
MUTATION = mutations("toolz")[1]
GRADER = """from toolz import first
assert first('xyz') == 'x'
assert first([None, 2]) is None
source = iter([7, 8, 9])
assert first(source) == 7
assert next(source) == 8
assert first(x for x in range(4)) == 0
try:
    first([])
except StopIteration:
    pass
else:
    raise AssertionError('first(empty) must raise StopIteration')
print('public-contract grader passed')
"""


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def public_hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): sha(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and not any(x.startswith(".") or x == "__pycache__" for x in p.relative_to(root).parts)
    }


def checked(root: Path, args: list[str]) -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    start = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, "-B", *args], cwd=root, env=env, capture_output=True, text=True, timeout=60
        )
        return {
            "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "wall_ms": (time.monotonic() - start) * 1000,
            "output": (result.stdout + result.stderr).replace(str(root), "<repository>")[-12000:],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "timeout_seconds": 60, "wall_ms": (time.monotonic() - start) * 1000}


def copy_source(destination: Path) -> None:
    shutil.copytree(
        SOURCE, destination, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
    )


def prepare() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = OUTPUT / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=SOURCE, text=True
    )
    if commit != REPO.commit or dirty:
        raise ValueError("Toolz source must be clean at the declared pin")
    state = OUTPUT / "shadow-state"
    state.mkdir()
    for name in ("policy.json", "report.json"):
        shutil.copy2(PROJECT / ".reflex" / name, state / name)
    policy = json.loads((state / "policy.json").read_text())
    policy["model"] = str((PROJECT / "models/adapted-v1").resolve())
    save(state / "policy.json", policy)
    transition(state, "shadow")
    runtime = OUTPUT / "runtime-snapshot"
    shutil.copytree(
        PROJECT / "src/reflexfoundry",
        runtime / "reflexfoundry",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (runtime / "reflex_cli.py").write_text("from reflexfoundry.cli import main\nraise SystemExit(main())\n")
    (OUTPUT / "public_contract_grader.py").write_text(GRADER)
    shutil.copy2(SOURCE / REPO.license_file, OUTPUT / "TOOLZ-LICENSE.txt")
    with tempfile.TemporaryDirectory(prefix="reflex-codex-preflight-", dir="/private/tmp") as temp:
        root = Path(temp) / "toolz"
        copy_source(root)
        clean = {"full": checked(root, ["-m", "pytest", "-q"]), "grader": checked(root, ["-c", GRADER])}
        path = root / REPO.source_file
        original = path.read_bytes()
        path.write_text(apply_mutation(original.decode(), MUTATION))
        mutant = {
            "focused": checked(root, ["-m", "pytest", "-q", REPO.test_file + "::test_first"]),
            "grader": checked(root, ["-c", GRADER]),
        }
        if not all(v["passed"] for v in clean.values()) or any(v["passed"] for v in mutant.values()):
            save(OUTPUT / "preflight-failure.json", {"clean": clean, "mutant": mutant})
            raise RuntimeError("clean/mutant preflight did not establish a repair task")
    value = {
        "format": 1,
        "design": "one public mutation; two paired repeats; alternating arm order",
        "repository": REPO.url,
        "commit": commit,
        "mutation": MUTATION.id,
        "order": ORDER,
        "python": sys.executable,
        "platform": platform.platform(),
        "codex_version": subprocess.check_output(["codex", "--version"], text=True).strip(),
        "model_and_effort": "inherited from existing Codex configuration; no override",
        "sandbox": "workspace-write",
        "max_cli_runs": 4,
        "run_timeout_seconds": 180,
        "baseline": clean,
        "mutant": mutant,
        "original_source_sha256": sha(original),
        "mutated_source_sha256": sha(apply_mutation(original.decode(), MUTATION).encode()),
        "source_files": public_hashes(SOURCE),
        "runtime_files": public_hashes(runtime),
        "policy_id": policy["id"],
        "policy_artifact_digest": policy["artifact_digest"],
        "policy_report_digest": policy["report_digest"],
        "deployment_allowed": policy["report"]["deployment_allowed"],
        "privacy": "Event lines processed in memory then discarded; only command names/counts, final answer, errors and public task artifacts retained.",
    }
    save(manifest, value)
    return value


def prompt(arm: str) -> str:
    base = f"""Repair Toolz's public first(seq) function in toolz/itertoolz.py. It must return the first element of a sequence or iterator, consume only that first item, and raise StopIteration for empty input. Inspect the current source and documented public contract. Make the smallest correct source repair; do not edit tests or unrelated files.

Use the existing interpreter {sys.executable}. After the repair run both normal official checks, in order:
{sys.executable} -B -m pytest -q toolz/tests/test_itertoolz.py::test_first
{sys.executable} -B -m pytest -q
Do not install dependencies, use network, inspect credentials, commit, or delegate. Use native sandbox tools. Finish with a concise report of the change and actual check results.
"""
    if arm == "shadow":
        base += f"""
Use the packaged $reflexfoundry skill in .agents/skills/reflexfoundry/SKILL.md for shadow advice. Public task input collection is authorized. After writing the repair and before validation, read the skill, run `{sys.executable} .reflex_runtime/reflex_cli.py specs`, create request.json from the actual task summary and changed relative source path, and run `{sys.executable} .reflex_runtime/reflex_cli.py decide request.json --workspace .reflex --backend torch > advisory.json`. Inspect advisory.json. Do not alter policy, report, runtime, guards or deployment. Keep the original two validation commands above regardless of fallback or candidate. Abstained or untested proposals have no verified shadow outcome; do not record one.
"""
    return base


def command_names(command: str) -> list[str]:
    """Count leading allowlisted binaries, including a documented shell wrapper."""
    try:
        parts = shlex.split(command)
        if len(parts) >= 3 and Path(parts[0]).name in {"zsh", "bash", "sh"} and "c" in parts[1]:
            parts = shlex.split(parts[2])
        names = []
        for index, token in enumerate(parts):
            if index == 0 or parts[index - 1] in {"&&", ";", "||", "|"}:
                name = Path(token).name
                if name.startswith("python"):
                    name = "python"
                if name in ALLOWED:
                    names.append(name)
        return names
    except ValueError:
        return []


def run(index: int, manifest: dict) -> dict:
    if index not in range(1, 5):
        raise ValueError("run index must be from one to four")
    folder = OUTPUT / f"run-{index:02}"
    folder.mkdir()  # No retries or silent overwrites of an attempt.
    repeat, arm = ORDER[index - 1]
    save(folder / "started.json", {"repeat": repeat, "arm": arm, "time_unix": time.time()})
    with tempfile.TemporaryDirectory(prefix=f"reflex-codex-{index}-", dir="/private/tmp") as temp:
        root = Path(temp) / "toolz"
        copy_source(root)
        target = root / REPO.source_file
        target.write_text(apply_mutation(target.read_text(), MUTATION))
        if arm == "shadow":
            shutil.copytree(OUTPUT / "shadow-state", root / ".reflex")
            shutil.copytree(OUTPUT / "runtime-snapshot", root / ".reflex_runtime")
            skill = root / ".agents/skills/reflexfoundry"
            shutil.copytree(PROJECT / "integrations/codex/skills/reflexfoundry", skill)
        request_prompt = prompt(arm)
        (folder / "prompt.txt").write_text(request_prompt)
        final = folder / "final-answer.txt"
        cmd = [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--json",
            "--color",
            "never",
            "-C",
            str(root),
            "-o",
            str(final),
            "-",
        ]
        save(folder / "invocation.json", {"argv": cmd, "cwd": str(root), "stdin": "prompt.txt"})
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
        start = time.monotonic()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=root,
            env=env,
            start_new_session=True,
        )
        proc.stdin.write(request_prompt.encode())
        proc.stdin.close()
        counts, total, errors, stderr = {}, 0, [], bytearray()
        timed_out = False
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "events")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        buffers = {"events": b"", "stderr": b""}
        while selector.get_map():
            if time.monotonic() - start > 185:
                # A child may have inherited a pipe. Never wait indefinitely
                # for EOF after the bounded Codex process has been stopped.
                for key in list(selector.get_map().values()):
                    selector.unregister(key.fileobj)
                break
            if time.monotonic() - start > 180 and proc.poll() is None:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
            for key, _ in selector.select(timeout=0.2):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    stderr.extend(chunk)
                    continue
                buffers["events"] += chunk
                while b"\n" in buffers["events"]:
                    line, buffers["events"] = buffers["events"].split(b"\n", 1)
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    item = event.get("item", {})
                    if event.get("type") == "item.completed" and item.get("type") == "command_execution":
                        total += 1
                        for name in command_names(item.get("command", "")):
                            counts[name] = counts.get(name, 0) + 1
                    elif event.get("type") in {"error", "turn.failed"}:
                        errors.append(event.get("message", event.get("error", {})))
                    # All other event fields, reasoning and freeform messages are discarded.
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        wall_ms = (time.monotonic() - start) * 1000
        (folder / "cli-stderr.txt").write_text(stderr.decode(errors="replace")[-12000:])
        repaired = target.read_bytes()
        (folder / "candidate-itertoolz.py").write_bytes(repaired)
        current = public_hashes(root)
        changed = [p for p, h in manifest["source_files"].items() if current.get(p) != h]
        extra = sorted(set(current) - set(manifest["source_files"]) - {"request.json", "advisory.json"})
        verification = {
            "focused": checked(root, ["-m", "pytest", "-q", REPO.test_file + "::test_first"]),
            "full": checked(root, ["-m", "pytest", "-q"]),
            "public_contract": checked(root, ["-c", GRADER]),
        }
        advisory = None
        if (root / "advisory.json").exists():
            try:
                advisory = json.loads((root / "advisory.json").read_text())
            except json.JSONDecodeError:
                advisory = {"invalid_json": True}
            shutil.copy2(root / "advisory.json", folder / "advisory.json")
        if (root / "request.json").exists():
            shutil.copy2(root / "request.json", folder / "request.json")
        answer = final.read_text() if final.exists() else ""
        result = {
            "run": index,
            "repeat": repeat,
            "arm": arm,
            "cli_exit_code": proc.returncode,
            "timed_out": timed_out,
            "wall_ms": wall_ms,
            "independent_wall_ms": sum(v["wall_ms"] for v in verification.values()),
            "agent_plus_independent_ms": wall_ms + sum(v["wall_ms"] for v in verification.values()),
            "errors": errors,
            "observable_commands": total,
            "allowlisted_command_counts": counts,
            "candidate_sha256": sha(repaired),
            "source_changed": changed,
            "extra_public_files": extra,
            "candidate_differs_from_mutant": sha(repaired) != manifest["mutated_source_sha256"],
            "independent": verification,
            "advisory": advisory,
            "final_answer_present": bool(answer),
            "success": (
                all(v["passed"] for v in verification.values())
                and sha(repaired) != manifest["mutated_source_sha256"]
                and set(changed) <= {REPO.source_file}
                and not extra
                and proc.returncode == 0
                and not timed_out
            ),
        }
        save(folder / "result.json", result)
        return result


def summarize() -> dict:
    rows = [json.loads(p.read_text()) for p in sorted(OUTPUT.glob("run-*/result.json"))]
    pairs = []
    for repeat in (1, 2):
        group = {r["arm"]: r for r in rows if r["repeat"] == repeat}
        if len(group) == 2 and all(row["success"] and row["cli_exit_code"] == 0 for row in group.values()):
            pairs.append(
                {
                    "repeat": repeat,
                    "shadow_minus_original_ms": group["shadow"]["wall_ms"] - group["original"]["wall_ms"],
                }
            )
    value = {
        "completed_cli_runs": len(rows),
        "successful_repairs": sum(r["success"] for r in rows),
        "paired_wall_time": pairs,
        "scope": "A small one-task native Codex CLI feasibility study; two repeats are not independent task diversity. Host/model variability, order and shared caches confound timing; no causal superiority claim.",
        "deployment": "withheld; original full workflow required in both arms",
    }
    save(OUTPUT / "summary.json", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-index", type=int)
    args = parser.parse_args()
    manifest = prepare()
    if not args.prepare_only:
        for index in [args.run_index] if args.run_index else range(1, 5):
            result = run(index, manifest)
            print(
                json.dumps({k: result[k] for k in ("run", "arm", "wall_ms", "cli_exit_code", "success")}),
                flush=True,
            )
            summarize()
            if result["errors"] or result["timed_out"]:
                break


if __name__ == "__main__":
    main()
