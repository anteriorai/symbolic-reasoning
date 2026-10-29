from symbolic_reasoning.gen.py.srg import (
    Aggregator,
    AllStrategy,
    AtLeastStrategy,
    AtMostStrategy,
    ExactlyStrategy,
    Strategy,
)


def evaluate_strategy(
    strategy: Strategy, evaluations: list[bool | None]
) -> bool | None:
    """
    Evaluate a strategy against a list of boolean evaluations that may include None.

    When all values are known this returns a definitive bool. When some values
    are None it returns a bool if the result can be determined by short-circuit
    logic (e.g. any False in an AllStrategy means the result is False),
    otherwise None.

    Args:
        strategy: The aggregation strategy to execute
        evaluations: List of boolean or None values to aggregate

    Returns:
        True/False if the result is determined, None if more data is needed

    Raises:
        TypeError: If strategy type is unknown
    """
    root = strategy.root

    true_count = evaluations.count(True)
    none_count = evaluations.count(None)

    if isinstance(root, AllStrategy):
        if any(e is False for e in evaluations):
            return False
        return None if none_count > 0 else True

    elif isinstance(root, AtLeastStrategy):
        if true_count >= root.count:
            return True
        if true_count + none_count < root.count:
            return False
        return None if none_count > 0 else true_count >= root.count

    elif isinstance(root, AtMostStrategy):
        if true_count > root.count:
            return False
        if true_count + none_count <= root.count:
            return True
        return None if none_count > 0 else true_count <= root.count

    elif isinstance(root, ExactlyStrategy):
        if true_count > root.count:
            return False
        if true_count + none_count < root.count:
            return False
        return None if none_count > 0 else true_count == root.count

    else:
        raise TypeError(f"Unknown strategy type: {type(root)}")


def get_aggregator_label(aggregator: Aggregator) -> str:
    """
    Get a human-readable label for an aggregator based on its strategy and truth value.

    Args:
        aggregator: The aggregator to generate a label for

    Returns:
        String label like "AllTrue", "AtLeast2False", etc.

    Raises:
        TypeError: If strategy type is unknown
    """
    truth_suffix = "True" if aggregator.truth_value else "False"
    strategy = aggregator.strategy.root
    if isinstance(strategy, AllStrategy):
        return f"All{truth_suffix}"
    elif isinstance(strategy, AtLeastStrategy):
        return f"AtLeast{strategy.count}{truth_suffix}"
    elif isinstance(strategy, AtMostStrategy):
        return f"AtMost{strategy.count}{truth_suffix}"
    elif isinstance(strategy, ExactlyStrategy):
        return f"Exactly{strategy.count}{truth_suffix}"
    else:
        raise TypeError(f"Unknown strategy type: {type(strategy)}")
