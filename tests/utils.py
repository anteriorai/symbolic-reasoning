"""Test utilities for SRG tests."""

from dataclasses import dataclass

from symbolic_reasoning import apply_answers, outcomes, reasoning_trace
from symbolic_reasoning.models import SRG, Answer, SRGExecution
from symbolic_reasoning.models.srg_execution import _all_distinct_paths, _outcome_paths
from symbolic_reasoning.solvers.solver import next_request

# ============================================================================
# Solver Scenario Types
# ============================================================================


@dataclass
class SolverStep:
    """One round-trip with the solver: the predicate IDs expected and the answers to submit."""

    expected_predicate_ids: list[str]
    answers: list[bool]


@dataclass
class SolverScenario:
    """Pure data describing one solver interaction: inputs (steps) and expected outputs (paths).

    The SRG under test is intentionally absent — it is provided separately by the caller
    (typically a pytest fixture), keeping scenario data independent of construction logic.

    expected_outcome_paths is a list of (outcome_description, predicate_ids) pairs.
    A scenario may produce multiple paths, including multiple paths to the same outcome.

    expected_distinct_paths is an optional list of predicate-ID lists corresponding to
    get_all_distinct_paths() output. Each inner list may contain duplicate IDs when a
    predicate appears in multiple aggregator subtrees.
    """

    steps: list[SolverStep]
    expected_outcome_paths: list[tuple[str, list[str]]]
    expected_distinct_paths: list[list[str]] | None = None


async def run_solver_scenario(srg: SRG, scenario: SolverScenario) -> None:
    """Drive the solver through all steps and assert the expected paths.

    The SRG is passed in separately so SolverScenario remains pure data.
    """
    execution = SRGExecution(srg=srg)
    request = next_request(execution)

    for step in scenario.steps:
        assert request is not None, "No request returned from solver"
        assert [
            p.predicate.id for p in request.predicate_requests
        ] == step.expected_predicate_ids
        execution = apply_answers(
            execution,
            {
                r.predicate.id: Answer(is_met=v, reasoning="yes")
                for r, v in zip(request.predicate_requests, step.answers, strict=True)
            },
        )
        request = next_request(execution)

    assert request is None

    actual_outcome_paths = sorted(
        (path[0].description, [pred.id for pred, _ in path[1]])
        for path in _outcome_paths(execution)
    )
    assert actual_outcome_paths == sorted(scenario.expected_outcome_paths)

    if scenario.expected_distinct_paths is not None:
        # Sort each path's predicate IDs (preserving duplicates), then sort the
        # collection so assertion order is deterministic.
        actual_distinct = sorted(
            sorted(pred.id for pred, _ in path)
            for path in _all_distinct_paths(execution)
        )
        expected_distinct = sorted(
            sorted(pids) for pids in scenario.expected_distinct_paths
        )
        assert actual_distinct == expected_distinct

    _assert_reasoning_trace(execution, scenario)


def _assert_reasoning_trace(execution: SRGExecution, scenario: SolverScenario) -> None:
    """Assert that the typed ReasoningTrace APIs agree with legacy results."""
    # explain() should produce the same outcome/predicate pairs as get_outcome_paths()
    typed_outcome_paths = sorted(
        (
            execution.srg.outcomes[t.outcome_id].description,
            [s.predicate_id for s in t.steps],
        )
        for t in reasoning_trace(execution).outcome_paths
    )
    assert typed_outcome_paths == sorted(scenario.expected_outcome_paths)

    # outcomes() should list unique outcomes matching expected set
    assert sorted(o.description for o in outcomes(execution)) == sorted(
        {desc for desc, _ in scenario.expected_outcome_paths}
    )

    # reasoning_trace().outcome_paths should match explain()
    trace = reasoning_trace(execution)
    assert trace.outcome_paths == reasoning_trace(execution).outcome_paths

    if scenario.expected_distinct_paths is not None:
        typed_distinct = sorted(
            sorted(s.predicate_id for s in t.steps) for t in trace.all_paths
        )
        expected_distinct = sorted(
            sorted(pids) for pids in scenario.expected_distinct_paths
        )
        assert typed_distinct == expected_distinct


def assert_no_dangling_references(srg: SRG) -> None:
    """
    Assert that all aggregator argument references are valid (no dangling references).

    Checks that every argument_id in every aggregator references a valid item
    (predicate, aggregator, or outcome) in the SRG.

    Args:
        srg: The SRG to check for dangling references

    Raises:
        AssertionError: If any aggregator has a dangling reference
    """
    for agg_id, agg in srg.aggregators.items():
        for arg_id in agg.argument_ids:
            assert arg_id in srg.predicates or arg_id in srg.aggregators, (
                f"Dangling reference: {agg_id} -> {arg_id}"
            )


def create_predicate_answers(srg: SRG, answer_pattern: str) -> dict[str, Answer]:
    """Create answers for all predicates in an SRG based on a pattern."""
    answers = {}

    for pred_id, predicate in srg.predicates.items():
        if answer_pattern == "all_true":
            answers[pred_id] = Answer(
                is_met=True, reasoning=f"{predicate.question} - Yes"
            )
        elif answer_pattern == "all_false":
            answers[pred_id] = Answer(
                is_met=False, reasoning=f"{predicate.question} - No"
            )
        elif answer_pattern == "alternating":
            # Alternate based on predicate ID hash
            is_met = hash(pred_id) % 2 == 0
            answers[pred_id] = Answer(
                is_met=is_met, reasoning=f"Pattern answer: {is_met}"
            )
        else:
            raise ValueError(f"Unknown answer pattern: {answer_pattern}")

    return answers


def assert_outcome_reached(execution: SRGExecution, expected_outcome: str) -> None:
    """Assert that a specific outcome is reached in the execution."""
    outcome_paths = _outcome_paths(execution)
    outcomes = [path[0].description for path in outcome_paths]
    assert expected_outcome in outcomes, f"Expected '{expected_outcome}' in {outcomes}"


def get_aggregator_by_name(srg: SRG, name: str) -> str:
    """Get aggregator ID by name."""
    for agg_id, aggregator in srg.aggregators.items():
        if aggregator.name == name:
            return agg_id
    raise ValueError(f"Aggregator with name '{name}' not found")


def asked(execution: SRGExecution) -> list[str]:
    """IDs of the predicates the next minimal request asks, in order."""
    request = next_request(execution)
    return (
        [] if request is None else [r.predicate.id for r in request.predicate_requests]
    )
