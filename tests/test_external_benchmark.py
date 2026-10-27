import pytest

from reflexfoundry.external_benchmark import REPOSITORIES, _outcomes, apply_mutation, mutations


def test_pinned_mutations_require_exact_anchor() -> None:
    assert len(REPOSITORIES) == 2
    assert all(len(repo.commit) == 40 for repo in REPOSITORIES)
    for repo in REPOSITORIES:
        assert len(mutations(repo.name)) == 3
        for mutation in mutations(repo.name):
            assert apply_mutation(mutation.before, mutation) == mutation.after
            with pytest.raises(ValueError):
                apply_mutation("source drifted", mutation)
            with pytest.raises(ValueError):
                apply_mutation(mutation.before * 2, mutation)


def test_independent_grading_and_repeated_timing() -> None:
    outcomes = _outcomes({
        "focused": [{"passed": True, "duration_ms": 12.0}, {"passed": True, "duration_ms": 14.0}],
        "full": [{"passed": False, "duration_ms": 20.0}, {"passed": False, "duration_ms": 22.0}],
    }, False)
    assert outcomes["focused"]["false_acceptance"]
    assert not outcomes["focused"]["success"]
    assert outcomes["full"]["success"]
    assert outcomes["full"]["duration_ms"] == 21
    with pytest.raises(RuntimeError):
        _outcomes({"full": [{"passed": True, "duration_ms": 1}, {"passed": False, "duration_ms": 2}]}, False)
