"""Prepare or execute one explicitly authorized native comparison attempt.

Preparation performs local public-source checks only. A run flag is not human
authority: do not launch a run without scoped user egress/call approval accepted
by the ordinary outer review control. The historical v1 study is untouched.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts"))
from native_retrieve_v2 import ARMS as WORKER_ARMS  # noqa: E402
from native_retrieve_v2 import RECEIPT_KEY, prediction  # noqa: E402
from native_study_tasks import TASKS, Task, copy_source, mutate_source, preflight, run_check  # noqa: E402

from reflexfoundry.codex import EventSummary  # noqa: E402
from reflexfoundry.core import digest, finite_number, privacy_filter  # noqa: E402
from reflexfoundry.lifecycle import _binding_valid, transition  # noqa: E402
from reflexfoundry.model import artifact_digest, file_hash  # noqa: E402

WHEEL_SHA256 = "c1aaf0946ffa7fb3136f5aee705c85dbd936fa505d553dbd5cfc975773fb9f5b"
MAX_RUNS, TIMEOUT, GRACE = 20, 180, 5
MAX_LINE, MAX_STREAM = 1024 * 1024, 8 * 1024 * 1024
ARMS = ("original-agent", *WORKER_ARMS[1:])
ORDER = tuple((task_index, repeat, arm)
              for repeat in (1, 2) for task_index in (0, 1)
              for arm in (ARMS if (repeat + task_index) % 2 else ARMS[::-1]))
MODEL_ARMS = frozenset({"ordinary-laya", "trained-always", "selective-shadow"})
TRAINED_ARMS = frozenset({"trained-always", "selective-shadow"})


def runtime_versions() -> dict[str, str]:
    return {"python": sys.version.split()[0], **{
        name: importlib.metadata.version(name) for name in ("laya", "torch", "transformers", "tokenizers")}}


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def inventory(root: Path, *, max_bytes: int = 2 * 1024**3, ignore_caches: bool = True) -> dict[str, str]:
    result: dict[str, str] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if ignore_caches and any(part in {"__pycache__", ".pytest_cache"} for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError("prepared artifacts must contain regular files, not links")
        if path.is_file():
            total += path.stat().st_size
            if total > max_bytes or len(result) >= 4096:
                raise ValueError("prepared artifacts exceed their file/byte bound")
            result[str(path.relative_to(root))] = file_hash(path)
    return result


def case_runtime_matches(case: Path, plan: dict[str, Any], item: dict[str, Any] | None = None) -> bool:
    """Check runtime bytes independently of source/pytest cache exclusions."""
    runtime = case / ".reflex_runtime"
    if item is not None and item["arm"] == "original-agent":
        forbidden = (".reflex_runtime", ".reflex", ".reflex_retrieve.py", ".reflex_case.json",
                     "request.json", ".agents/skills/reflexfoundry")
        files = item["initial_files"]
        return (not any((case / prefix).exists() or (case / prefix).is_symlink() for prefix in forbidden)
                and files == item["public_source_files"]
                and not any(name == prefix or name.startswith(prefix + "/")
                            for name in files for prefix in forbidden))
    if not runtime.is_dir() or runtime.is_symlink():
        return False
    try:
        return inventory(runtime, ignore_caches=False) == plan["runtime_files"]
    except (OSError, ValueError):
        return False


def expected_call(command: Any, executable: str) -> bool:
    """Recognize only the exact standalone retrieval command, without eval."""
    if not isinstance(command, str) or len(command.encode()) > 65536:
        return False
    for _ in range(4):
        try:
            words = shlex.split(command)
        except ValueError:
            return False
        if words == [executable, "-B", ".reflex_retrieve.py"]:
            return True
        if len(words) != 3 or Path(words[0]).name not in {"sh", "bash", "zsh"} or words[1] not in {"-c", "-lc"}:
            return False
        command = words[2]
    return False


def extract_receipts(output: Any) -> tuple[list[dict[str, Any]], int, int]:
    """Keep only fixed structured fields from the expected command's output."""
    if not isinstance(output, str) or len(output.encode()) > MAX_LINE:
        return [], 0, 1
    fields = {"format", "arm", "request_digest", "source_sha256", "runtime_digest", "cli_sha256",
              "model_artifact_digest", "policy_sha256", "report_sha256", "decision_contract_digest",
              "inference_observed", "prediction", "prediction_digest", "choice", "context_digest",
              "step_wall_ms", "policy_call_ms", "identity_audit_ms"}
    required_hashes = {"request_digest", "source_sha256", "runtime_digest", "cli_sha256",
                       "decision_contract_digest", "context_digest"}
    optional_hashes = {"model_artifact_digest", "policy_sha256", "report_sha256", "prediction_digest"}
    receipts: list[dict[str, Any]] = []
    seen = rejected = 0
    for line in output.splitlines():
        if not line.lstrip().startswith('{"' + RECEIPT_KEY + '":'):
            continue
        try:
            outer = json.loads(line)
            value = outer[RECEIPT_KEY]
            if set(outer) != {RECEIPT_KEY} or not isinstance(value, dict) or set(value) != fields:
                raise ValueError("receipt fields differ from the declared allowlist")
            if (type(value["format"]) is not int or value["format"] != 1 or value["arm"] not in WORKER_ARMS
                    or value["choice"] not in {"symbol", "search"} or not isinstance(value["inference_observed"], bool)):
                raise ValueError("invalid receipt metadata")
            for key in required_hashes | optional_hashes:
                text = value[key]
                if key in optional_hashes and text is None:
                    continue
                if not isinstance(text, str) or len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
                    raise ValueError("invalid receipt identity")
            for key in ("step_wall_ms", "policy_call_ms", "identity_audit_ms"):
                if not finite_number(value[key]) or not 0 <= value[key] <= (TIMEOUT + GRACE) * 1000:
                    raise ValueError("invalid receipt timing")
            raw = value["prediction"]
            if raw is not None and (prediction(raw) != raw or value["prediction_digest"] != digest(raw)):
                raise ValueError("invalid or empty prediction")
            if raw is None and (value["prediction_digest"] is not None or value["inference_observed"]):
                raise ValueError("inference requires a complete actual prediction")
            if value["arm"] not in MODEL_ARMS and (raw is not None or value["inference_observed"]):
                raise ValueError("deterministic arms do not invoke a model")
            seen += 1
            if len(receipts) < 2:
                receipts.append(value)
        except (ValueError, KeyError, TypeError, OverflowError):
            rejected += 1
    return receipts, seen, rejected


def receipt_matches(receipt: dict[str, Any], item: dict[str, Any], plan: dict[str, Any], context: dict[str, Any]) -> bool:
    """Cross-check observed stdout against frozen identities and file content."""
    arm = item["arm"]
    expected = {"arm": arm, "request_digest": item["request_digest"],
                "source_sha256": item["mutated_source_sha256"], "runtime_digest": digest(plan["runtime_files"]),
                "cli_sha256": plan["runtime_files"]["reflex_cli.py"],
                "decision_contract_digest": plan["decision_contract_digest"],
                "model_artifact_digest": plan["base_artifact_digest"] if arm == "ordinary-laya" else
                    plan["model_artifact_digest"] if arm in TRAINED_ARMS else None,
                "policy_sha256": plan["policy_sha256"] if arm in TRAINED_ARMS else None,
                "report_sha256": plan["report_sha256"] if arm in TRAINED_ARMS else None}
    try:
        if any(receipt.get(key) != value for key, value in expected.items()) or digest(context) != receipt["context_digest"]:
            return False
        if (context.get("prediction") != receipt["prediction"] or context.get("choice") != receipt["choice"]
                or context.get("source_sha256") != receipt["source_sha256"]):
            return False
        if arm in MODEL_ARMS and (not receipt["inference_observed"] or prediction(receipt["prediction"]) is None):
            return False
        if arm in {"ordinary-laya", "trained-always"} and receipt["choice"] != receipt["prediction"]["choice"]:
            return False
        if arm in TRAINED_ARMS:
            advisory = context["advisory"]
            if (not isinstance(advisory, dict) or advisory.get("mode") != "shadow"
                    or advisory.get("reason") != "shadow observation"
                    or prediction(advisory.get("prediction")) != receipt["prediction"]):
                return False
            if arm == "selective-shadow" and advisory.get("choice") != receipt["choice"]:
                return False
        if arm == "original-search" and receipt["choice"] != "search":
            return False
        if arm == "deterministic-heuristic":
            task = next(task for task in TASKS if task.name == item["task"])
            if receipt["choice"] != ("symbol" if task.context_inputs.get("symbol", "").strip() else "search"):
                return False
    except (ValueError, KeyError, TypeError, OverflowError):
        return False
    return True


def assess_retrieval(item: dict[str, Any], plan: dict[str, Any], context: dict[str, Any],
                     observed: dict[str, Any]) -> dict[str, bool]:
    """Require no benchmark helper for the undelegated original-agent arm."""
    if item["arm"] == "original-agent":
        valid = (observed["retrieval_command_attempts"] == 0 and observed["expected_retrieval_calls"] == 0
                 and observed["retrieval_receipts_seen"] == 0 and not observed["retrieval_receipts"]
                 and not observed["rejected_receipts"] and not context)
        return {"retrieval_protocol_valid": valid, "observed_receipt_valid": False, "inference_observed": False}
    receipts = observed["retrieval_receipts"]
    valid = (observed["retrieval_command_attempts"] == 1 and observed["expected_retrieval_calls"] == 1
             and observed["retrieval_receipts_seen"] == 1 and len(receipts) == 1
             and not observed["rejected_receipts"] and receipt_matches(receipts[0], item, plan, context))
    inference = bool(valid and receipts[0]["inference_observed"])
    return {"retrieval_protocol_valid": valid and (item["arm"] not in MODEL_ARMS or inference),
            "observed_receipt_valid": valid, "inference_observed": inference}


def prompt(task: Task, arm: str, executable: str) -> str:
    prefix = f"PYTHONPATH={shlex.quote(task.import_root)} "
    focused = prefix + shlex.join([executable, "-B", *task.focused_args])
    full = prefix + shlex.join([executable, "-B", *task.full_args])
    if arm == "original-agent":
        return (f"{task.repair_contract}\n\n"
                "Use your normal native tools to inspect the source and make the smallest correct repair. "
                "Do not edit tests or unrelated source.\n\n"
                f"After the smallest source repair run both unchanged official checks, in order:\n{focused}\n{full}\n"
                "Both checks remain mandatory. Do not install dependencies, use network, inspect credentials, "
                "commit, or delegate. Keep native permissions and sandbox intact. "
                "Finish with a concise change and actual-check report.\n")
    skill = ("Read .agents/skills/reflexfoundry/SKILL.md before the retrieval step. "
             if arm in MODEL_ARMS else "")
    return (f"{task.repair_contract}\n\n"
            f"{skill}Before editing source, run this exact standalone command once:\n"
            f"{shlex.join([executable, '-B', '.reflex_retrieve.py'])}\n"
            "Read context-result.json. This is the declared initial source-retrieval action. "
            "You may inspect additional source with normal native tools. "
            "Do not modify request.json, .reflex_case.json, .reflex_retrieve.py, .reflex_runtime, "
            ".reflex, the skill, tests, or unrelated source. Do not fabricate an advisory. "
            "Public task input collection is authorized; no policy deployment or outcome attestation is authorized.\n\n"
            "Some research arms measure unguarded local choices only for this declared read-only retrieval on a public copy. "
            "This never activates a failed policy or changes permission authority.\n\n"
            f"After the smallest source repair run both unchanged official checks, in order:\n{focused}\n{full}\n"
            "Both checks remain mandatory regardless of the retrieval choice or fallback. "
            "Do not install dependencies, use network, inspect credentials, commit, or delegate. "
            "Keep native permissions and sandbox intact. Finish with a concise change and actual-check report.\n")


def source_hashes() -> dict[str, str]:
    names = ("scripts/native_study_v2.py", "scripts/native_retrieve_v2.py", "scripts/native_study_tasks.py",
             "src/reflexfoundry/codex.py")
    return {name: file_hash(PROJECT / name) for name in names}


def build_case(task: Task, source: Path, case: Path, arm: str,
               runtime: Path, template: Path, base: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Keep the original-agent case exactly public source, without helpers."""
    if arm not in ARMS:
        raise ValueError("unsupported native study arm")
    public = copy_source(task, source, case)
    target = case / task.source_file
    target.write_text(mutate_source(task, target.read_text()))
    public[task.source_file] = file_hash(target)
    if arm != "original-agent":
        shutil.copytree(runtime, case / ".reflex_runtime", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(PROJECT / "scripts/native_retrieve_v2.py", case / ".reflex_retrieve.py")
        save(case / "request.json", task.request)
        save(case / ".reflex_case.json", {"arm": arm, "request": task.request,
            "repository_name": task.repository_name, "commit": task.commit,
            "source_file": task.source_file, "mutated_source_sha256": public[task.source_file],
            "base_model": str(base.resolve())})
        if arm in TRAINED_ARMS:
            shutil.copytree(template, case / ".reflex")
        if arm in MODEL_ARMS:
            shutil.copytree(PROJECT / "integrations/codex/skills/reflexfoundry", case / ".agents/skills/reflexfoundry")
    files = inventory(case, max_bytes=32 * 1024**2)
    if arm == "original-agent" and files != public:
        raise ValueError("undelegated original-agent case contains benchmark artifacts")
    return files, public


def prepare(sources: Path, stage: Path, policy_workspace: Path, output: Path, wheel: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("study preparation requires a fresh output directory")
    if file_hash(wheel) != WHEEL_SHA256:
        raise ValueError("runtime wheel differs from the verified public 0.2.1 release")
    runtime, model, base = stage / "runtime", stage / "model", stage / "base"
    runtime_files = inventory(runtime, ignore_caches=False)
    with zipfile.ZipFile(wheel) as archive:
        public = {name: hashlib.sha256(archive.read(name)).hexdigest()
                  for name in archive.namelist() if name.startswith("reflexfoundry/") and not name.endswith("/")}
    if any(runtime_files.get(name) != value for name, value in public.items()):
        raise ValueError("staged runtime does not match public wheel contents")
    allowed = set(public) | {"reflex_cli.py"}
    if set(runtime_files) != allowed:
        raise ValueError("runtime contains unexpected files")
    if (runtime / "reflex_cli.py").read_text() != "from reflexfoundry.cli import main\nraise SystemExit(main())\n":
        raise ValueError("runtime CLI entry point changed")
    policy = json.loads((policy_workspace / "policy.json").read_text())
    report = json.loads((policy_workspace / "report.json").read_text())
    if (Path(policy["model"]).resolve() != model.resolve() or report.get("backend") != "torch"
            or policy.get("report_digest") != digest(report) or not _binding_valid(policy, "context-route-v1")):
        raise ValueError("need a fresh valid CPU evaluation bound to the staged model")
    model_manifest = json.loads((model / "manifest.json").read_text())
    if file_hash(base / "model.safetensors") != model_manifest["base_weights_sha256"]:
        raise ValueError("untuned base does not match trained-head provenance")
    output.mkdir(parents=True)
    preflights = {}
    for task in TASKS:
        preflights[task.name] = preflight(task, sources / task.repository_name, output / "preflight" / f"{task.name}.json")
    template = output / "shadow-template"
    template.mkdir()
    for name in ("policy.json", "report.json"):
        shutil.copy2(policy_workspace / name, template / name)
    transition(template, "shadow")
    cases = stage / "cases"
    cases.mkdir(exist_ok=False)
    plans = []
    for index, (task_index, repeat, arm) in enumerate(ORDER, 1):
        task = TASKS[task_index]
        case = cases / f"{index:02}-{task.name}"
        files, public = build_case(task, sources / task.repository_name, case, arm, runtime, template, base)
        text = prompt(task, arm, sys.executable)
        prompt_file = output / "prompts" / f"{index:02}.txt"
        prompt_file.parent.mkdir(exist_ok=True)
        prompt_file.write_text(text)
        plans.append({"index": index, "task": task.name, "repeat": repeat, "arm": arm,
                      "case": str(case.resolve()), "prompt_sha256": file_hash(prompt_file),
                      "request_digest": digest(task.request), "mutated_source_sha256": public[task.source_file],
                      "public_source_files": public, "initial_files": files})
    version = subprocess.check_output(["codex", "--version"], text=True, stderr=subprocess.DEVNULL).strip()
    if version != "codex-cli 0.165.0":
        raise ValueError("CLI version changed; review the protocol before freezing it")
    plan = {"format": 2, "status": "prepared-not-authorized", "native_processes_started": 0,
            "max_native_attempts": MAX_RUNS, "run_timeout_seconds": TIMEOUT, "shutdown_grace_seconds": GRACE,
            "executable": sys.executable, "codex_version": version, "stage": str(stage.resolve()),
            "runtime_release": "v0.2.1", "runtime_wheel_sha256": WHEEL_SHA256,
            "runtime_files": runtime_files, "model_files": inventory(model),
            "base_files": inventory(base), "base_artifact_digest": artifact_digest(base),
            "versions": runtime_versions(), "arms": ARMS,
            "model_artifact_digest": artifact_digest(model), "decision_contract_digest": policy["decision_contract_digest"],
            "policy_sha256": file_hash(template / "policy.json"), "report_sha256": file_hash(template / "report.json"),
            "source_hashes": source_hashes(), "tasks": [asdict(task) for task in TASKS], "order": plans,
            "preflight_passed": all(value["preflight_passed"] for value in preflights.values()),
            "model_and_effort": "Inherited native configuration; no override or credential inspection.",
            "authority": "Run flags do not grant authority. Direct scoped human egress/call approval and ordinary outer review are required.",
            "privacy": "Only public task artifacts, final visible answer, numeric usage and command counts retained; no raw event stream, reasoning, arguments, or stderr text.",
            "scope": "Two controlled public repair tasks, five declared arms and two paired repeats;20 new calls max. Original-agent is a bare public-source case with normal context tools, no benchmark artifacts. Raw always-choice arms are read-only research counterfactuals, never policy deployment. Not a powered population or causal benefit claim. Old v1 study remains unchanged.",
            "receipt_boundary": "Only an allowlisted structured receipt from the successful exact worker command's observed stdout supports inference; writable context/advisory files alone never do. This is observational evidence, not cryptographic attestation.",
            "sandbox": "Explicit documented workspace-write per case; native permission system/rules/model/effort remain intact, without bypass flags.",
            "cost_boundary": "Primary pipeline wall time starts immediately before Popen and ends after independent focused/full/grader checks. Readiness hashing and postcondition auditing are separate, with attempt-all-in through report assembly. Final result writing and study/model/case preparation are excluded. Readiness checks warm caches; host load and caches limit timing generalization."}
    save(output / "plan.json", plan)
    return plan


def validate_plan(plan: dict[str, Any], output: Path) -> None:
    stage = Path(plan["stage"])
    if plan.get("max_native_attempts") != MAX_RUNS or len(plan["order"]) != MAX_RUNS:
        raise ValueError("native budget or fixed order changed")
    actual_order = [(item["task"], item["repeat"], item["arm"]) for item in plan["order"]]
    expected_order = [(TASKS[index].name, repeat, arm) for index, repeat, arm in ORDER]
    if actual_order != expected_order or list(plan["arms"]) != list(ARMS):
        raise ValueError("declared five-arm order changed")
    version = subprocess.check_output(["codex", "--version"], text=True, stderr=subprocess.DEVNULL).strip()
    if version != plan["codex_version"] or sys.executable != plan["executable"]:
        raise ValueError("CLI or interpreter changed after preparation")
    if plan["source_hashes"] != source_hashes():
        raise ValueError("study or telemetry source changed after preparation")
    if (inventory(stage / "runtime", ignore_caches=False) != plan["runtime_files"] or inventory(stage / "model") != plan["model_files"]
            or inventory(stage / "base") != plan["base_files"]):
        raise ValueError("frozen runtime or model files changed")
    if artifact_digest(stage / "model") != plan["model_artifact_digest"]:
        raise ValueError("model inference identity changed")
    if artifact_digest(stage / "base") != plan["base_artifact_digest"] or runtime_versions() != plan["versions"]:
        raise ValueError("base identity or runtime versions changed")
    template = output / "shadow-template"
    if file_hash(template / "policy.json") != plan["policy_sha256"] or file_hash(template / "report.json") != plan["report_sha256"]:
        raise ValueError("frozen policy or report changed")
    if not _binding_valid(json.loads((template / "policy.json").read_text()), "context-route-v1"):
        raise ValueError("prepared policy binding is no longer valid")


def stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return  # Reap an already terminal child; do not signal a stale group.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=2)


def observe_process(proc: subprocess.Popen[bytes], executable: str, *, started: float | None = None) -> dict[str, Any]:
    telemetry = EventSummary()
    matched, invalid, event_errors = 0, 0, 0
    retrieval_attempts = 0
    receipts: list[dict[str, Any]] = []
    receipts_seen = rejected_receipts = 0
    stdout_bytes, stderr_bytes, buffer = 0, 0, b""
    stderr_hash = hashlib.sha256()
    started = time.perf_counter() if started is None else started
    timed_out = overflow = False
    selector = selectors.DefaultSelector()
    assert proc.stdout is not None and proc.stderr is not None
    selector.register(proc.stdout, selectors.EVENT_READ, "events")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    while selector.get_map():
        elapsed = time.perf_counter() - started
        if elapsed > TIMEOUT and not timed_out:
            timed_out = True
            stop(proc)
        if elapsed > TIMEOUT + GRACE:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            break
        for key, _ in selector.select(timeout=.2):
            chunk = os.read(key.fd, 65536)
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            if key.data == "stderr":
                stderr_bytes += len(chunk)
                stderr_hash.update(chunk)
                if stdout_bytes + stderr_bytes > MAX_STREAM:
                    overflow = True
                    stop(proc)
                    break
                continue
            stdout_bytes += len(chunk)
            buffer += chunk
            if stdout_bytes + stderr_bytes > MAX_STREAM or len(buffer) > MAX_LINE:
                overflow = True
                stop(proc)
                break
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    event = json.loads(line)
                    telemetry.observe(event)
                    if event.get("type") in {"error", "turn.failed"}:
                        event_errors += 1
                    item = event.get("item", {})
                    if (event.get("type") == "item.completed" and isinstance(item, dict)
                            and item.get("type") == "command_execution"
                            and expected_call(item.get("command"), executable)):
                        retrieval_attempts += 1
                        if type(item.get("exit_code")) is int and item["exit_code"] == 0:
                            matched += 1
                            captured, count, bad = extract_receipts(item.get("aggregated_output"))
                            receipts_seen += count
                            rejected_receipts += bad
                            receipts.extend(captured[:max(0, 2 - len(receipts))])
                except (ValueError, TypeError, UnicodeDecodeError):
                    invalid += 1
            if overflow:
                break
        if overflow:
            break
    selector.close()
    if buffer.strip():
        invalid += 1  # A partial final event is not fabricated into telemetry.
    if proc.poll() is None:
        stop(proc)
    return {"telemetry": telemetry.result(), "expected_retrieval_calls": matched,
            "retrieval_command_attempts": retrieval_attempts,
            "retrieval_receipts": receipts, "retrieval_receipts_seen": receipts_seen,
            "rejected_receipts": rejected_receipts,
            "invalid_events": invalid, "event_errors": event_errors, "timed_out": timed_out,
            "stream_limit_exceeded": overflow, "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes, "stderr_sha256": stderr_hash.hexdigest(),
            "cli_exit_code": proc.returncode, "cli_wall_ms": (time.perf_counter() - started) * 1000}


def run(index: int, output: Path, *, consent_egress: bool = False) -> dict[str, Any]:
    if not consent_egress:
        raise ValueError("execution requires scoped human approval plus --consent-egress; a flag alone is not authority")
    if isinstance(index, bool) or index not in range(1, MAX_RUNS + 1):
        raise ValueError("run index must be from 1 to 20")
    started = time.perf_counter()
    plan = json.loads((output / "plan.json").read_text())
    validate_plan(plan, output)
    attempts = output / "attempts"
    for previous in range(1, index):
        path = attempts / f"{previous:02}" / "result.json"
        if not path.exists() or json.loads(path.read_text()).get("protocol_failure"):
            raise ValueError("previous attempt is incomplete or failed protocol; stop for review")
    item = plan["order"][index - 1]
    case, task = Path(item["case"]), next(task for task in TASKS if task.name == item["task"])
    if inventory(case, max_bytes=32 * 1024**2) != item["initial_files"] or not case_runtime_matches(case, plan, item):
        raise ValueError("prepared case changed before its only allowed attempt")
    prompt_file = output / "prompts" / f"{index:02}.txt"
    if file_hash(prompt_file) != item["prompt_sha256"]:
        raise ValueError("prepared prompt changed")
    folder = attempts / f"{index:02}"
    folder.mkdir(parents=True, exist_ok=False)  # A failed attempt is never silently retried.
    save(folder / "started.json", {"index": index, "time_unix": time.time(), "native_process_started": False})
    final = folder / "final-answer.txt"
    cmd = ["codex", "exec", "--ephemeral", "--sandbox", "workspace-write", "--skip-git-repo-check",
           "--json", "--color", "never", "-C", str(case), "-o", str(final.resolve()), "-"]
    save(folder / "invocation.json", {"argv": cmd, "prompt_sha256": item["prompt_sha256"], "external_authority_required": True})
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    launch_started = time.perf_counter()
    try:
        proc = subprocess.Popen(cmd, cwd=case, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        result = {"index": index, "task": task.name, "repeat": item["repeat"], "arm": item["arm"],
                  "native_process_started": False, "protocol_failure": True, "task_success": False,
                  "pipeline_wall_ms": None, "readiness_ms": (launch_started - started) * 1000,
                  "attempt_all_in_ms": (time.perf_counter() - started) * 1000,
                  "failure": "native process could not start; no retry"}
        save(folder / "result.json", result)
        return result
    save(folder / "started.json", {"index": index, "time_unix": time.time(), "native_process_started": True})
    assert proc.stdin is not None
    with contextlib.suppress(BrokenPipeError):
        proc.stdin.write(prompt_file.read_bytes())
        proc.stdin.close()
    result = observe_process(proc, plan["executable"], started=launch_started)
    verification = {"focused": run_check(task, case, task.focused_args),
                    "full": run_check(task, case, task.full_args)}
    grader = folder / "independent-grader.py"
    grader.write_text(task.grader)
    verification["public_contract"] = run_check(task, case, (str(grader.resolve()),))
    verification_finished = time.perf_counter()
    try:
        current = inventory(case, max_bytes=32 * 1024**2)
    except (OSError, ValueError):
        current = {}
    allowed_new = set() if item["arm"] == "original-agent" else {"context-result.json", "advisory.json", ".reflex/requests.json"}
    extra = set(current) - set(item["initial_files"]) - allowed_new
    changed = {name for name, value in item["initial_files"].items() if current.get(name) != value}
    unchanged = not extra and changed <= {task.source_file} and case_runtime_matches(case, plan, item)
    context = {}
    context_file = case / "context-result.json"
    if context_file.is_file() and not context_file.is_symlink() and context_file.stat().st_size <= 128 * 1024:
        try:
            value = json.loads(context_file.read_text())
            if isinstance(value, dict):
                context = value
        except (ValueError, UnicodeDecodeError):
            pass
    retrieval = assess_retrieval(item, plan, context, result)
    try:
        validate_plan(plan, output)
        frozen = True
    except ValueError:
        frozen = False
    receipt_valid = retrieval["observed_receipt_valid"] and unchanged and frozen
    inference = retrieval["inference_observed"] and unchanged and frozen
    usage = result["telemetry"]["token_usage"]
    protocol_ok = (result["telemetry"]["completed_turns"] == 1
                   and usage is not None and not result["invalid_events"] and not result["event_errors"]
                   and not result["timed_out"] and not result["stream_limit_exceeded"]
                   and result["cli_exit_code"] == 0 and unchanged and frozen
                   and retrieval["retrieval_protocol_valid"] and (item["arm"] not in MODEL_ARMS or inference))
    result.update(index=index, task=task.name, repeat=item["repeat"], arm=item["arm"],
                  native_process_started=True, protocol_failure=not protocol_ok,
                  retrieval_protocol_valid=retrieval["retrieval_protocol_valid"] and unchanged and frozen,
                  inference_observed=inference, observed_receipt_valid=receipt_valid,
                  immutable_files_preserved=unchanged and frozen,
                  independent=verification, task_success=all(check["passed"] for check in verification.values()),
                  context=context, changed_public_files=sorted(changed), extra_files=sorted(extra),
                  pipeline_wall_ms=(verification_finished - launch_started) * 1000,
                  readiness_ms=(launch_started - started) * 1000,
                  candidate_sha256=current.get(task.source_file))
    target = case / task.source_file
    if target.is_file() and not target.is_symlink() and target.stat().st_size <= 2 * 1024**2:
        shutil.copy2(target, folder / "candidate.py")
    if final.exists():
        with final.open() as handle:
            answer = handle.read(12000)
        final.write_text(privacy_filter({"summary": answer})["summary"])
    assembled = time.perf_counter()
    result["postcondition_audit_ms"] = (assembled - verification_finished) * 1000
    result["attempt_all_in_ms"] = (assembled - started) * 1000
    save(folder / "result.json", result)
    return result


def summarize(output: Path) -> dict[str, Any]:
    """Describe all attempts; failed repairs are never filtered into success."""
    rows = [json.loads(path.read_text()) for path in sorted((output / "attempts").glob("*/result.json"))]
    starts = [json.loads(path.read_text()) for path in sorted((output / "attempts").glob("*/started.json"))]
    pairs = []
    for task in TASKS:
        for repeat in (1, 2):
            group = {row["arm"]: row for row in rows if row["task"] == task.name and row["repeat"] == repeat}
            for arm in ARMS[1:]:
                if "original-agent" not in group or arm not in group:
                    continue
                original, candidate = group["original-agent"], group[arm]
                if original["protocol_failure"] or candidate["protocol_failure"]:
                    continue
                original_usage = original["telemetry"]["token_usage"]
                candidate_usage = candidate["telemetry"]["token_usage"]
                pairs.append({"task": task.name, "repeat": repeat, "arm": arm,
                              "original_success": original["task_success"], "candidate_success": candidate["task_success"],
                              "success_delta": int(candidate["task_success"]) - int(original["task_success"]),
                              "arm_minus_original_pipeline_ms": candidate["pipeline_wall_ms"] - original["pipeline_wall_ms"],
                              "arm_minus_original_cli_ms": candidate["cli_wall_ms"] - original["cli_wall_ms"],
                              "token_deltas": {key: candidate_usage[key] - original_usage[key]
                                               for key in ("input_tokens", "cached_input_tokens", "output_tokens")}})
    value = {"reserved_attempts": len(starts), "native_processes_started": sum(row["native_process_started"] for row in starts),
             "completed_attempts": len(rows), "task_successes": sum(row["task_success"] for row in rows),
             "protocol_failures": sum(row["protocol_failure"] for row in rows),
             "model_inference_observations": sum(row.get("inference_observed", False) for row in rows),
             "all_planned_attempts_complete": len(rows) == MAX_RUNS, "paired_comparisons": pairs,
             "all_planned_comparisons_valid": len(rows) == MAX_RUNS and not any(row["protocol_failure"] for row in rows),
             "independent_repository_groups": len({row["task"] for row in pairs}),
             "currency_cost": None, "deployment": "withheld; full validation mandatory",
             "uncertainty": "Two actual repositories with correlated repeats; no population reliability or causal superiority claim. Missing/protocol-failed pairs remain visible and provide no paired estimate."}
    save(output / "summary.json", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run-index", type=int)
    mode.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--stage", type=Path, default=Path("/private/tmp/reflexfoundry-native-v2"))
    parser.add_argument("--policy-workspace", type=Path, default=PROJECT / "runs/native-v2-preparation")
    parser.add_argument("--output", type=Path, default=PROJECT / "runs/native-v2-study")
    parser.add_argument("--runtime-wheel", type=Path, default=Path("/private/tmp/reflexfoundry-0.2.1-public-verify-f19e691/reflexfoundry-0.2.1-py3-none-any.whl"))
    parser.add_argument("--consent-egress", action="store_true", help="necessary execution opt-in, not a substitute for human/review authority")
    args = parser.parse_args()
    if args.prepare_only:
        if args.sources is None or args.consent_egress:
            parser.error("local preparation needs --sources and must not assert execution consent")
        value = prepare(args.sources.resolve(), args.stage.resolve(), args.policy_workspace.resolve(),
                        args.output.resolve(), args.runtime_wheel.resolve())
        print(json.dumps({key: value[key] for key in ("status", "max_native_attempts", "native_processes_started")}))
    elif args.summarize_only:
        if args.consent_egress:
            parser.error("local summary must not assert execution consent")
        print(json.dumps(summarize(args.output.resolve())))
    else:
        value = run(args.run_index, args.output.resolve(), consent_egress=args.consent_egress)
        summarize(args.output.resolve())
        print(json.dumps({key: value[key] for key in ("index", "arm", "task_success", "protocol_failure")}))


if __name__ == "__main__":
    main()
