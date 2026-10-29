"""Retrieval mechanics and retained public-source evidence, without fetching code."""
import hashlib
import json
from pathlib import Path

import pytest

from reflexfoundry.context_benchmark import (
    MAX_FILE_BYTES,
    REPOSITORIES,
    SNIPPET_BYTES,
    TARGETS,
    Repository,
    Target,
    _corpus,
    generate,
    grade,
    symbol_lookup,
    text_search,
)


def test_lookup_handles_qualified_symbols_without_executing_source(tmp_path: Path) -> None:
    sentinel = tmp_path / "should-not-exist"
    source = f'''raise RuntimeError({str(sentinel)!r})
class Catalog:
    def lookup(self, key):
        """Look up one named item."""
        return key
'''
    corpus = {"package/catalog.py": source}
    target = Target("Catalog.lookup", "package/catalog.py", "def lookup(self, key):", "Look up one named item.")
    request = {"summary": "Locate implementation", "symbol": "Catalog.lookup", "changed_files": []}
    assert grade(target, symbol_lookup(corpus, request))
    assert not sentinel.exists()
    assert symbol_lookup(corpus, {"summary": "Look up one named item."}) == []
    assert symbol_lookup(corpus, {"summary": "Look up one named item.", "symbol": "missing"}) == []


def test_literal_retrieval_and_grader_have_separate_boundaries() -> None:
    corpus = {"package/catalog.py": 'def lookup(key):\n    """Look up one named item."""\n    return key\n'}
    target = Target("lookup", "package/catalog.py", "def lookup(key):", "Look up one named item.")
    snippets = text_search(corpus, {"summary": "Look up one named item.", "changed_files": []})
    assert grade(target, snippets)
    assert not grade(target, [{"path": "another.py", "text": snippets[0]["text"]}])
    assert not grade(target, [{"path": target.path, "text": target.contract}])
    assert not grade(target, [])
    assert snippets[0]["sha256"] == hashlib.sha256(snippets[0]["text"].encode()).hexdigest()


def test_snippet_byte_budget_and_hint_priority() -> None:
    long_source = 'def lookup():\n    """Contract."""\n' + ('    # ' + 'é' * 800 + '\n') * 10
    corpus = {"a.py": long_source, "b.py": long_source}
    result = symbol_lookup(corpus, {"summary": "lookup", "symbol": "lookup", "changed_files": ["b.py"]})
    assert result[0]["path"] == "b.py"
    assert len(result[0]["text"].encode()) <= SNIPPET_BYTES
    assert len(text_search(corpus, {"summary": "Contract."})) <= 3


def test_source_boundaries_do_not_follow_links_or_read_unbounded_files(tmp_path: Path) -> None:
    repo = Repository("sample", "https://example.com/public", "unused", "package", "LICENSE", "train")
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("def target(): pass\n")
    (package / "link.py").symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        _corpus(repo, tmp_path)
    (package / "link.py").unlink()
    (package / "large.py").write_text("#" * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="byte bound"):
        _corpus(repo, tmp_path)


def test_invalid_or_reused_output_is_rejected_before_source_access(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repeats"):
        generate(tmp_path / "fresh", {}, repeats=True)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "preserved.txt"
    marker.write_text("existing evidence")
    with pytest.raises(FileExistsError, match="fresh"):
        generate(output, {})
    assert marker.read_text() == "existing evidence"
    with pytest.raises(ValueError, match="missing public source"):
        generate(tmp_path / "fresh", {})


def test_retained_experiment_preserves_real_groups_and_observed_evidence() -> None:
    output = Path(__file__).resolve().parents[1] / "benchmarks/context-v1/scoped-v1"
    blob = (output / "records.jsonl").read_bytes()
    rows = [json.loads(line) for line in blob.splitlines()]
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["records_sha256"] == hashlib.sha256(blob).hexdigest()
    assert manifest["counts"] == {"train": 42, "calibration": 30, "promotion": 30, "test": 30}
    assert manifest["deployment_allowed"] is False
    for repo in REPOSITORIES:
        subset = [row for row in rows if row["split"] == repo.split]
        assert {row["repository"] for row in subset} == {repo.url}
        assert len({row["task_group"] for row in subset}) == len(TARGETS[repo.name]) == 6
        provenance = next(item for item in manifest["repositories"] if item["name"] == repo.name)
        assert provenance["commit"] == repo.commit
        assert provenance["corpus_startup_ms"] > 0
        license_bytes = (output / "licenses" / f"{repo.name}.txt").read_bytes()
        assert provenance["license_sha256"] == hashlib.sha256(license_bytes).hexdigest()
    from reflexfoundry.core import validate_splits
    validate_splits(rows, require_evaluation_outcomes=True)
    for row in rows:
        assert row["spec"] == "context-route-v1"
        assert row["inputs"]["changed_files"] == []
        assert "path" not in row["inputs"]
        startup = next(repo["corpus_startup_ms"] for repo in manifest["repositories"] if repo["url"] == row["repository"])
        for outcome in row["outcomes"].values():
            assert outcome["duration_ms"] == outcome["median_action_ms"] + startup
            assert outcome["corpus_startup_ms"] == startup
        evidence = json.loads((output / row["oracle"]["evidence"]).read_text())
        assert len(evidence["orders"]) == manifest["repeats"] == 3
        assert evidence["orders"][0] == evidence["orders"][1][::-1]
        for choice in ("symbol", "search"):
            assert len(evidence["trials"][choice]) == 3
            for trial in evidence["trials"][choice]:
                assert trial["duration_ms"] > 0
                assert trial["success"] == row["outcomes"][choice]["success"]
                assert grade(Target(**row["oracle"]["target"]), trial["snippets"]) == trial["success"]
                for snippet in trial["snippets"]:
                    assert snippet["sha256"] == hashlib.sha256(snippet["text"].encode()).hexdigest()
