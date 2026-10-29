"""Scientific diagnostic invariants, without actual models or native processes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import choice_stress as stress  # noqa: E402


def test_expanded_orders_balance_alias_positions_but_are_not_exhaustive():
    condition = stress.conditions()[-1]
    assert len(condition["orders"]) == 4 < condition["all_possible_orders"] == 24
    for key in condition["criteria"]:
        assert {order.index(key) for order in condition["orders"]} == set(range(4))
    assert all(condition["criteria"][key] == condition["criteria"][action]
               for key, action in condition["action_mapping"].items())


def test_sampling_uses_ids_not_outcomes_and_only_the_test_split():
    rows = []
    for group in range(6):
        for number in (2, 0, 1):
            rows.append({"id": f"{group}-{number}", "task_group": str(group), "repository": "same-public-repo",
                         "split": "test", "spec": "context-route-v1", "inputs": {}, "outcomes": {"ignored": number}})
    rows.append(rows[0] | {"id": "not-test", "split": "train"})
    first = stress.sample(rows)
    second = stress.sample([row | {"outcomes": {"changed": True}} for row in rows[::-1]])
    assert len(first) == 12
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert all(row["id"].endswith(("-0", "-2")) for row in first)


def response(choice="symbol", probabilities=None, truncated=False):
    probabilities = probabilities or {"symbol": .4, "search": .3, "symbol_duplicate": .01, "search_duplicate": .29}
    return {"answers": {"decision": {"choice": choice, "probabilities": probabilities}},
            "usage": {"truncated": truncated}, "unknown": "MUST-NOT-BE-RETAINED"}


def test_individual_winner_is_not_replaced_by_aggregate_action_mass():
    result = stress.parse_response(response(), stress.conditions()[-1])
    assert result["choice"] == result["action"] == "symbol"
    assert result["summed_mass_winner"] == "search"
    assert result["action_probability_mass"]["search"] == pytest.approx(.59)
    assert "MUST-NOT" not in json.dumps(result)


@pytest.mark.parametrize("bad", [None, {}, {"answers": {}},
    response(probabilities={"symbol": .6, "search": .4}),
    response(probabilities={"symbol": True, "search": 0, "symbol_duplicate": 0, "search_duplicate": 0}),
    response(probabilities={"symbol": .8, "search": .8, "symbol_duplicate": 0, "search_duplicate": 0})])
def test_malformed_decision_is_not_silently_accepted(bad):
    with pytest.raises(ValueError):
        stress.parse_response(bad, stress.conditions()[-1])


def test_summary_keeps_invalid_and_truncated_observations_and_enforces_completeness():
    condition = stress.conditions()[0]
    plan = {"models": {"model": "hash"}, "inputs": [{"id": "input"}], "conditions": [condition],
            "planned_predictions": 2, "limits": []}
    prediction = stress.parse_response(response(probabilities={"symbol": .6, "search": .4}, truncated=True), condition)
    valid = {"model": "model", "input_id": "input", "condition": condition["name"], "order_index": 0,
             "error": None, "prediction": prediction, "retained_context_covered": False}
    invalid = valid | {"order_index": 1, "error": "malformed_response", "prediction": None,
                       "retained_context_covered": None}
    result = stress.summarize(plan, [valid, invalid])
    assert result["retained_predictions"] == 2 and result["incomplete_or_invalid_predictions"] == 1
    assert result["per_input"][0]["truncated_responses"] == 1
    assert result["aggregate"][0]["inputs_with_missing_or_truncated_observation"] == 1
    assert result["population_confidence_interval"] is None
    for observations in ([valid], [valid, valid], [valid, invalid, invalid]):
        with pytest.raises(ValueError, match="every planned observation"):
            stress.summarize(plan, observations)


@pytest.mark.parametrize("usage", [None, {}, {"truncated": "unknown"}])
def test_missing_usage_retains_valid_decision_without_inventing_truncation(usage):
    result = stress.parse_response(response() | {"usage": usage}, stress.conditions()[-1])
    assert result["choice"] == "symbol"
    assert result["action_probability_mass"]["search"] == pytest.approx(.59)
    assert result["truncated"] is None
