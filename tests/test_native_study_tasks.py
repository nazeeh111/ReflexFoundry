"""Native-study fixture boundaries without fetching or executing public code."""
import importlib.util
import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[1] / "scripts/native_study_tasks.py"
_spec = importlib.util.spec_from_file_location("native_study_tasks", _path)
assert _spec and _spec.loader
tasks = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tasks
_spec.loader.exec_module(tasks)


def test_mutations_have_exact_single_anchors_and_bounded_public_inputs():
    for task in tasks.TASKS:
        assert len(task.commit) == 40
        assert tasks.mutate_source(task, task.mutation_before) == task.mutation_after
        with pytest.raises(ValueError, match="anchor"):
            tasks.mutate_source(task, task.mutation_before * 2)
        with pytest.raises(ValueError, match="anchor"):
            tasks.mutate_source(task, "source changed")
        assert task.request["spec"] == "context-route-v1"
        assert task.context_inputs["changed_files"] == []
        assert set(task.context_inputs) == {"summary", "changed_files", "symbol"}
        assert task.repository_name in task.context_inputs["summary"]
        assert task.source_file not in task.context_inputs["summary"]


def test_src_layout_checks_import_candidate_not_an_installed_package(tmp_path):
    task = tasks.TASKS[1]
    package = tmp_path / task.package
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("candidate_marker = 'local public fixture'\n")
    result = tasks.run_check(task, tmp_path, ("-c",
        "import cachetools; assert cachetools.candidate_marker == 'local public fixture'"))
    assert result["passed"]


def test_independent_checks_ignore_candidate_bytecode_even_with_matching_timestamp(tmp_path):
    task = tasks.TASKS[0]
    package = tmp_path / "funcy"
    package.mkdir()
    source = package / "__init__.py"
    source.write_text("VALUE = 9\n")
    os.utime(source, (1_000_000_000, 1_000_000_000))
    py_compile.compile(str(source), doraise=True)
    source.write_text("VALUE = 1\n")
    os.utime(source, (1_000_000_000, 1_000_000_000))
    baseline = subprocess.run([sys.executable, "-B", "-c", "import funcy; print(funcy.VALUE)"],
        cwd=tmp_path, env={"PYTHONPATH": str(tmp_path)}, capture_output=True, text=True, check=True)
    assert baseline.stdout.strip() == "9"  # -B alone does not prevent stale reads.
    checked = tasks.run_check(task, tmp_path, ("-c", "import funcy; assert funcy.VALUE == 1"))
    assert checked["passed"]


def test_existing_preflight_evidence_is_preserved_before_source_access(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("preserved evidence")
    with pytest.raises(FileExistsError, match="fresh"):
        tasks.preflight(tasks.TASKS[0], tmp_path / "missing-source", output)
    assert output.read_text() == "preserved evidence"


def test_internal_public_guidance_links_are_materialized_but_external_links_refused(tmp_path, monkeypatch):
    task = tasks.TASKS[0]
    source = tmp_path / "source"
    source.mkdir()
    target = source / task.source_file
    target.parent.mkdir(parents=True)
    target.write_text(task.mutation_before)
    (source / task.license_file).write_text("public license fixture")
    (source / "CLAUDE.md").write_text("public repository guidance fixture")
    (source / "AGENTS.md").symlink_to("CLAUDE.md")
    names = (task.source_file, task.license_file, "CLAUDE.md", "AGENTS.md")
    def git_output(args, **_kwargs):
        if args[1] == "rev-parse":
            return task.commit + "\n"
        if args[1] == "status":
            return ""
        if args[1] == "ls-files":
            return ("\0".join(names) + "\0").encode()
        raise AssertionError("unexpected Git command")
    monkeypatch.setattr(tasks.subprocess, "check_output", git_output)
    copied = tmp_path / "copied"
    tasks.copy_source(task, source, copied)
    assert not (copied / "AGENTS.md").is_symlink()
    assert (copied / "AGENTS.md").read_bytes() == (source / "CLAUDE.md").read_bytes()
    (source / "AGENTS.md").unlink()
    outside = tmp_path / "outside"
    outside.write_text("must not be included")
    (source / "AGENTS.md").symlink_to(outside)
    with pytest.raises(ValueError, match="within their checkout"):
        tasks.source_inventory(task, source)
