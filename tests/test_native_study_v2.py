"""Native-study controls using Python test doubles; no Codex/model execution."""
from __future__ import annotations

import json
import py_compile
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import native_study_v2 as study  # noqa: E402


@pytest.mark.parametrize("command,matched", [
    ("{python} -B .reflex_retrieve.py", True),
    ('/bin/zsh -lc "{python} -B .reflex_retrieve.py"', True),
    ("{python} -B .reflex_retrieve.py && echo done", False),
    ("echo '{python} -B .reflex_retrieve.py'", False),
    ("env PRIVATE=value {python} -B .reflex_retrieve.py", False),
    ("{python} .reflex_retrieve.py", False),
    ("sh -c 'unterminated", False),
])
def test_exact_retrieval_observation_does_not_count_incidental_shell_text(command, matched):
    assert study.expected_call(command.format(python=sys.executable), sys.executable) is matched


def test_run_requires_explicit_flag_before_reading_state_or_starting_process(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("a native process must not start")
    monkeypatch.setattr(study.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="scoped human approval"):
        study.run(1, tmp_path)
    with pytest.raises(ValueError, match="from 1 to 20"):
        study.run(21, tmp_path, consent_egress=True)
    assert not list(tmp_path.iterdir())


def python_event_process(events, *, stderr="PRIVATE-STDERR"):
    # A local Python stream fixture, not a native agent or model call.
    program = "import sys\n" + "\n".join(f"print({json.dumps(json.dumps(event))})" for event in events)
    program += f"\nsys.stderr.write({stderr!r})\n"
    return subprocess.Popen([sys.executable, "-c", program], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)


def test_stream_summary_keeps_counters_not_event_contents():
    proc = python_event_process([
        {"type": "item.completed", "item": {"type": "reasoning", "text": "PRIVATE-REASONING"}},
        {"type": "item.completed", "item": {"type": "command_execution", "exit_code": 0,
             "command": f"{sys.executable} -B .reflex_retrieve.py", "aggregated_output": "PRIVATE-OUTPUT"}},
        {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 20,
             "output_tokens": 10, "reasoning_output_tokens": 3, "unknown": "PRIVATE-USAGE"}},
    ])
    result = study.observe_process(proc, sys.executable)
    assert result["expected_retrieval_calls"] == 1
    assert result["telemetry"]["token_usage"]["input_tokens"] == 100
    assert result["stderr_bytes"] > 0
    assert "PRIVATE" not in json.dumps(result)
    assert proc.poll() == 0


def test_stream_limit_stops_python_fixture_without_persisting_output(monkeypatch):
    monkeypatch.setattr(study, "MAX_STREAM", 64)
    proc = python_event_process([{"type": "unknown", "text": "PRIVATE" * 100}])
    result = study.observe_process(proc, sys.executable)
    assert result["stream_limit_exceeded"]
    assert proc.poll() is not None
    assert "PRIVATE" not in json.dumps(result)


def test_combined_stderr_and_stdout_are_bounded(monkeypatch):
    monkeypatch.setattr(study, "MAX_STREAM", 64)
    proc = python_event_process([{"type": "unknown"}], stderr="x" * 50)
    result = study.observe_process(proc, sys.executable)
    assert result["stream_limit_exceeded"]
    assert result["stdout_bytes"] + result["stderr_bytes"] > 64


def test_cli_wall_time_includes_work_before_observation_starts():
    started = time.perf_counter()
    proc = python_event_process([])
    time.sleep(.02)
    result = study.observe_process(proc, sys.executable, started=started)
    assert result["cli_wall_ms"] >= 20


def test_wall_timeout_stops_python_fixture(monkeypatch):
    monkeypatch.setattr(study, "TIMEOUT", .05)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    result = study.observe_process(proc, sys.executable)
    assert result["timed_out"]
    assert proc.poll() is not None


def test_summary_retains_failed_repairs_in_valid_pairs(tmp_path):
    task = study.TASKS[0]
    for index, arm in enumerate(("original-agent", "selective-shadow"), 1):
        folder = tmp_path / "attempts" / f"{index:02}"
        study.save(folder / "started.json", {"native_process_started": True})
        study.save(folder / "result.json", {"task": task.name, "repeat": 1, "arm": arm,
            "task_success": index == 2, "protocol_failure": False, "inference_observed": index == 2,
            "pipeline_wall_ms": index * 100, "cli_wall_ms": index * 80,
            "telemetry": {"token_usage": {"input_tokens": index * 10, "cached_input_tokens": 0,
                                           "output_tokens": 5}}})
    result = study.summarize(tmp_path)
    assert result["native_processes_started"] == 2
    assert result["task_successes"] == 1
    assert result["paired_comparisons"][0]["success_delta"] == 1
    assert result["all_planned_attempts_complete"] is False
    assert result["currency_cost"] is None


@pytest.mark.parametrize("arm", ["original-search", "deterministic-heuristic", "selective-shadow"])
def test_worker_distinguishes_real_retrieval_from_cli_refusal(tmp_path, arm):
    runtime = tmp_path / ".reflex_runtime"
    shutil.copytree(SCRIPTS.parent / "src/reflexfoundry", runtime / "reflexfoundry",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # This CLI double deliberately has no prediction, so no model runs.
    (runtime / "reflex_cli.py").write_text("import json\nprint(json.dumps({'choice':'search',"
        "'mode':'shadow','fallback':True,'reason':'binding refused'}))\n")
    task = study.TASKS[0]
    (tmp_path / "funcy").mkdir()
    target = tmp_path / "funcy/seqs.py"
    target.write_text('def first(seq):\n    """The first item."""\n    return next(iter(seq), None)\n')
    study.save(tmp_path / ".reflex_case.json", {"arm": arm, "request": task.request,
               "repository_name": task.repository_name, "commit": task.commit,
               "source_file": task.source_file, "mutated_source_sha256": study.file_hash(target)})
    study.save(tmp_path / "request.json", task.request)
    if arm == "selective-shadow":
        model = tmp_path / "test-only-model"
        model.mkdir()
        (model / "model.safetensors").write_bytes(b"not a model; never loaded")
        (model / "rl_agent_config.json").write_text("{}")
        for directory in ("encoder", "tokenizer"):
            (model / directory).mkdir()
            (model / directory / "config.json").write_text("{}")
        study.save(tmp_path / ".reflex/policy.json", {"model": str(model)})
        study.save(tmp_path / ".reflex/report.json", {"test_only": True})
    result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "native_retrieve_v2.py")],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    receipt = json.loads(result.stdout)[study.RECEIPT_KEY]
    assert receipt["inference_observed"] is False
    assert receipt["source_sha256"] == study.file_hash(target)
    context = json.loads((tmp_path / "context-result.json").read_text())
    assert context["choice"] == ("symbol" if arm == "deterministic-heuristic" else "search")
    assert context["snippets"]
    assert context["inference_observed"] is False
    assert context["advisory"] is None if arm != "selective-shadow" else context["advisory"]["reason"] == "binding refused"


def receipt_fixture(arm="original-search", context=None):
    context = context or {"choice": "search", "prediction": None, "source_sha256": "a" * 64}
    return {"format": 1, "arm": arm, "request_digest": "a" * 64, "source_sha256": "a" * 64,
        "runtime_digest": "a" * 64, "cli_sha256": "a" * 64, "decision_contract_digest": "a" * 64,
        "context_digest": study.digest(context), "model_artifact_digest": None, "policy_sha256": None,
        "report_sha256": None, "inference_observed": False, "prediction": None,
        "prediction_digest": None, "choice": "search", "step_wall_ms": 1.0,
        "policy_call_ms": 0.0, "identity_audit_ms": 0.0}


def test_receipt_parser_does_not_accept_empty_prediction_or_private_fields():
    valid = receipt_fixture()
    parsed, seen, rejected = study.extract_receipts(json.dumps({study.RECEIPT_KEY: valid}))
    assert parsed == [valid] and seen == 1 and rejected == 0
    for changes in ({"prediction": {}, "prediction_digest": study.digest({}), "inference_observed": True},
                    {"unknown": "PRIVATE-SECRET"}, {"step_wall_ms": True}):
        result = study.extract_receipts(json.dumps({study.RECEIPT_KEY: valid | changes}))
        assert result == ([], 0, 1)
        assert "PRIVATE" not in json.dumps(result)


def test_mutable_context_file_cannot_replace_observed_receipt():
    context = {"choice": "search", "prediction": None, "source_sha256": "a" * 64}
    plan = {"runtime_files": {"reflex_cli.py": "a" * 64}, "decision_contract_digest": "a" * 64,
            "model_artifact_digest": "b" * 64, "base_artifact_digest": "c" * 64,
            "policy_sha256": "d" * 64, "report_sha256": "e" * 64}
    item = {"arm": "original-search", "request_digest": "a" * 64,
            "mutated_source_sha256": "a" * 64, "task": study.TASKS[0].name}
    receipt = receipt_fixture(context=context) | {"runtime_digest": study.digest(plan["runtime_files"])}
    assert study.receipt_matches(receipt, item, plan, context)
    assert not study.receipt_matches(receipt, item, plan, context | {"choice": "symbol"})
    assert not study.receipt_matches(receipt | {"runtime_digest": "f" * 64}, item, plan, context)


def test_stdout_receipt_is_captured_only_from_successful_exact_command():
    receipt = receipt_fixture()
    events = [{"type": "item.completed", "item": {"type": "command_execution", "exit_code": code,
               "command": command, "aggregated_output": json.dumps({study.RECEIPT_KEY: receipt})}}
              for code, command in ((1, f"{sys.executable} -B .reflex_retrieve.py"),
                                    (0, "echo .reflex_retrieve.py"),
                                    (0, f"{sys.executable} -B .reflex_retrieve.py"))]
    proc = python_event_process(events)
    observed = study.observe_process(proc, sys.executable)
    assert observed["expected_retrieval_calls"] == 1
    assert observed["retrieval_receipts_seen"] == 1
    assert observed["retrieval_receipts"] == [receipt]


def test_five_arm_order_is_balanced_without_extra_attempts():
    assert len(study.ORDER) == study.MAX_RUNS == 20
    for task in (0, 1):
        first = [arm for index, repeat, arm in study.ORDER if index == task and repeat == 1]
        second = [arm for index, repeat, arm in study.ORDER if index == task and repeat == 2]
        assert set(first) == set(study.ARMS)
        assert first == second[::-1]


def test_worker_refuses_retrieval_after_source_edit_before_loading_runtime(tmp_path):
    from native_retrieve_v2 import retrieve
    target = tmp_path / "source.py"
    target.write_text("before edit")
    expected = study.file_hash(target)
    target.write_text("after edit")
    study.save(tmp_path / ".reflex_case.json", {"arm": "original-search",
               "source_file": "source.py", "mutated_source_sha256": expected})
    with pytest.raises(ValueError, match="exact prepared mutant before editing"):
        retrieve(tmp_path)
    assert not (tmp_path / "context-result.json").exists()


def test_native_prompt_has_one_mandatory_validation_block_for_every_arm():
    for arm in study.ARMS:
        text = study.prompt(study.TASKS[0], arm, sys.executable)
        assert text.count("After the smallest source repair run both unchanged official checks") == 1
        assert "Both checks remain mandatory" in text


def test_original_agent_prompt_does_not_force_benchmark_context_retrieval():
    text = study.prompt(study.TASKS[0], "original-agent", sys.executable)
    assert "normal native tools" in text
    assert all(name not in text for name in (".reflex", "request.json", "context-result.json", "retrieval step", "skill"))
    assert "original-agent" in study.ARMS and "original-search" not in study.ARMS
    assert study.WORKER_ARMS[0] == "original-search"  # Component control, not the native baseline.


def test_original_agent_preparation_contains_exactly_public_mutant_source(tmp_path, monkeypatch):
    task = study.TASKS[0]
    source, case = tmp_path / "public-source", tmp_path / "case"
    target = source / task.source_file
    target.parent.mkdir(parents=True)
    target.write_text(f"def first(seq):\n    {task.mutation_before}\n")
    (source / "README.txt").write_text("public repository fixture")
    original = study.inventory(source)
    def copy_fixture(_task, supplied, destination):
        shutil.copytree(supplied, destination)
        return study.inventory(destination)
    monkeypatch.setattr(study, "copy_source", copy_fixture)
    missing = tmp_path / "no-benchmark-runtime-or-policy-needed"
    files, public = study.build_case(task, source, case, "original-agent", missing, missing, missing)
    assert files == public
    assert set(files) == set(original)
    assert files[task.source_file] != original[task.source_file]
    assert files["README.txt"] == original["README.txt"]
    item = {"arm": "original-agent", "initial_files": files, "public_source_files": public}
    assert study.case_runtime_matches(case, {}, item)
    assert not study.case_runtime_matches(case, {"runtime_files": {}})
    bad = item | {"initial_files": files | {"request.json": "a" * 64}}
    assert not study.case_runtime_matches(case, {}, bad)
    (case / ".reflex_runtime").mkdir()
    assert not study.case_runtime_matches(case, {}, item)


@pytest.mark.parametrize("fault", [None, "failed-helper-attempt", "successful-helper", "helper-context-file"])
def test_original_agent_requires_no_helper_calls_receipts_or_inference(fault):
    observed = {"retrieval_command_attempts": 0, "expected_retrieval_calls": 0,
                "retrieval_receipts_seen": 0, "retrieval_receipts": [], "rejected_receipts": 0}
    context = {}
    if fault == "failed-helper-attempt":
        observed["retrieval_command_attempts"] = 1
    elif fault == "successful-helper":
        observed.update(retrieval_command_attempts=1, expected_retrieval_calls=1,
                        retrieval_receipts_seen=1, retrieval_receipts=[receipt_fixture()])
    elif fault == "helper-context-file":
        context = {"choice": "search"}
    evidence = study.assess_retrieval({"arm": "original-agent"}, {}, context, observed)
    assert evidence["retrieval_protocol_valid"] is (fault is None)
    assert not evidence["observed_receipt_valid"] and not evidence["inference_observed"]


@pytest.mark.parametrize("cache", ["matching", "__pycache__/model.cpython-312.pyc", "model.pyc",
                                   "model.pyo", "__pycache__/unexpected.txt"])
def test_runtime_cache_refusal_precedes_frozen_imports_and_cli(tmp_path, monkeypatch, cache):
    import builtins

    from native_retrieve_v2 import retrieve
    task = study.TASKS[0]
    target = tmp_path / task.source_file
    target.parent.mkdir(parents=True)
    target.write_text("def first(seq): return None\n")
    runtime = tmp_path / ".reflex_runtime"
    package = runtime / "reflexfoundry"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise AssertionError('frozen package imported')\n")
    if cache == "matching":
        module = package / "model.py"
        module.write_text("raise AssertionError('compiled module executed')\n")
        py_compile.compile(str(module), doraise=True)
    else:
        forbidden = package / cache
        forbidden.parent.mkdir(parents=True, exist_ok=True)
        forbidden.write_bytes(b"dummy runtime cache")
    study.save(tmp_path / "request.json", task.request)
    study.save(tmp_path / ".reflex_case.json", {"arm": "selective-shadow", "request": task.request,
               "repository_name": task.repository_name, "commit": task.commit,
               "source_file": task.source_file, "mutated_source_sha256": study.file_hash(target)})
    original_import = builtins.__import__
    attempted = []
    def observe_import(name, *args, **kwargs):
        if name.startswith("reflexfoundry"):
            attempted.append(name)
            pytest.fail("runtime cache must be refused before importing runtime/model code")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", observe_import)
    before_path = list(sys.path)
    with pytest.raises(ValueError, match="bytecode|__pycache__"):
        retrieve(tmp_path)
    assert attempted == []
    assert sys.path == before_path
    assert not (tmp_path / "context-result.json").exists()
    assert not (tmp_path / "advisory.json").exists()


def test_case_runtime_comparison_catches_caches_ignored_for_public_sources(tmp_path):
    runtime = tmp_path / ".reflex_runtime"
    module = runtime / "reflexfoundry/model.py"
    module.parent.mkdir(parents=True)
    module.write_text("# test-only source, never imported\n")
    plan = {"runtime_files": study.inventory(runtime, ignore_caches=False)}
    original_case = study.inventory(tmp_path)
    assert study.case_runtime_matches(tmp_path, plan)
    cached = module.parent / "__pycache__/model.cpython-312.pyc"
    cached.parent.mkdir()
    cached.write_bytes(b"unexpected executable cache")
    assert study.inventory(tmp_path) == original_case
    assert not study.case_runtime_matches(tmp_path, plan)
    assert "reflexfoundry/__pycache__/model.cpython-312.pyc" in study.inventory(runtime, ignore_caches=False)


def test_empty_runtime_cache_directory_is_not_an_executable_cache(tmp_path):
    from native_retrieve_v2 import require_clean_runtime, runtime_inventory
    runtime = tmp_path / ".reflex_runtime"
    (runtime / "reflexfoundry/__pycache__").mkdir(parents=True)
    require_clean_runtime(runtime)
    assert runtime_inventory(runtime) == {}
