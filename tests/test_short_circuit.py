import pytest

from symbolic_reasoning.models import (
    AllStrategy,
    AtLeastStrategy,
    AtMostStrategy,
    ExactlyStrategy,
    Strategy,
)
from symbolic_reasoning.models.aggregator_logic import evaluate_strategy

# ============================================================================
# 1. evaluate_strategy with partial inputs
# ============================================================================


class TestEvaluateStrategyPartial:
    """Test evaluate_strategy with None values (partial / short-circuit evaluation)."""

    # -- AllStrategy --

    def test_all_with_one_false_short_circuits(self) -> None:
        assert (
            evaluate_strategy(Strategy(root=AllStrategy()), [True, False, None])
            is False
        )

    def test_all_with_all_true_and_none_is_undetermined(self) -> None:
        assert (
            evaluate_strategy(Strategy(root=AllStrategy()), [True, None, True]) is None
        )

    def test_all_fully_true(self) -> None:
        assert (
            evaluate_strategy(Strategy(root=AllStrategy()), [True, True, True]) is True
        )

    def test_all_fully_false(self) -> None:
        assert evaluate_strategy(Strategy(root=AllStrategy()), [False, False]) is False

    def test_all_with_all_none(self) -> None:
        assert evaluate_strategy(Strategy(root=AllStrategy()), [None, None]) is None

    # -- AtLeastStrategy --

    def test_atleast_threshold_met_early(self) -> None:
        result = evaluate_strategy(
            Strategy(root=AtLeastStrategy(count=2)), [True, True, None]
        )
        assert result is True

    def test_atleast_impossible_to_meet(self) -> None:
        result = evaluate_strategy(
            Strategy(root=AtLeastStrategy(count=3)), [True, False, None]
        )
        assert result is False

    def test_atleast_still_undetermined(self) -> None:
        result = evaluate_strategy(
            Strategy(root=AtLeastStrategy(count=2)), [True, None, None]
        )
        assert result is None

    def test_atleast_fully_resolved(self) -> None:
        assert (
            evaluate_strategy(
                Strategy(root=AtLeastStrategy(count=2)), [True, True, False]
            )
            is True
        )
        assert (
            evaluate_strategy(
                Strategy(root=AtLeastStrategy(count=2)), [True, False, False]
            )
            is False
        )

    # -- AtMostStrategy --

    def test_atmost_exceeded(self) -> None:
        result = evaluate_strategy(
            Strategy(root=AtMostStrategy(count=1)), [True, True, None]
        )
        assert result is False

    def test_atmost_guaranteed_under(self) -> None:
        result = evaluate_strategy(
            Strategy(root=AtMostStrategy(count=2)), [True, None, False]
        )
        assert result is True

    def test_atmost_still_undetermined(self) -> None:
        result = evaluate_strategy(
            Strategy(root=AtMostStrategy(count=1)), [True, None, None]
        )
        assert result is None

    def test_atmost_fully_resolved(self) -> None:
        assert (
            evaluate_strategy(
                Strategy(root=AtMostStrategy(count=1)), [True, False, False]
            )
            is True
        )
        assert (
            evaluate_strategy(
                Strategy(root=AtMostStrategy(count=1)), [True, True, False]
            )
            is False
        )

    # -- ExactlyStrategy --

    def test_exactly_count_exceeded(self) -> None:
        result = evaluate_strategy(
            Strategy(root=ExactlyStrategy(count=1)), [True, True, None]
        )
        assert result is False

    def test_exactly_impossible_to_reach(self) -> None:
        result = evaluate_strategy(
            Strategy(root=ExactlyStrategy(count=3)), [True, False, None]
        )
        assert result is False

    def test_exactly_still_undetermined(self) -> None:
        result = evaluate_strategy(
            Strategy(root=ExactlyStrategy(count=2)), [True, None, None]
        )
        assert result is None

    def test_exactly_fully_resolved(self) -> None:
        assert (
            evaluate_strategy(
                Strategy(root=ExactlyStrategy(count=2)), [True, True, False]
            )
            is True
        )
        assert (
            evaluate_strategy(
                Strategy(root=ExactlyStrategy(count=2)), [True, False, False]
            )
            is False
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
