"""A strategy reloads as itself, or fails to load; it never becomes another strategy."""

from typing import Any

import pytest
from pydantic import ValidationError

from symbolic_reasoning import SRG, compile_srg_string


def _compiled(operator: str) -> SRG:
    return compile_srg_string(
        f'predicate a: "A?"\npredicate b: "B?"\noutcome o: "O"\npath p: {operator} => o'
    )


@pytest.mark.parametrize(
    "operator", ["all(a, b)", "atleast(1, a, b)", "atmost(1, a, b)", "exactly(1, a, b)"]
)
def test_strategy_round_trips(operator: str) -> None:
    graph = _compiled(operator)

    reloaded = SRG.model_validate_json(graph.model_dump_json())

    assert reloaded.aggregators == graph.aggregators


@pytest.mark.parametrize(
    "strategy", [{}, {"count": 1}, {"type": "Unknown", "count": 1}]
)
def test_strategy_without_a_known_type_is_rejected(strategy: dict[str, Any]) -> None:
    payload = _compiled("atmost(1, a, b)").model_dump(mode="json")
    for aggregator in payload["aggregators"].values():
        aggregator["strategy"] = strategy

    with pytest.raises(ValidationError):
        SRG.model_validate(payload)
