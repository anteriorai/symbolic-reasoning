"""Resolution guarding: interpreting an execution requires it to be resolved."""

from collections.abc import Callable
from typing import Any

import pytest

from symbolic_reasoning import (
    SRGBuilder,
    apply_answers,
    is_resolved,
    outcomes,
    reasoning_trace,
)
from symbolic_reasoning.models import (
    SRG,
    AllStrategy,
    Answer,
    ExecutionNotResolvedError,
    SRGExecution,
)
from symbolic_reasoning.models.srg_execution import (
    _all_distinct_paths,
    _next_needed_predicates,
    _outcome_paths,
)
from symbolic_reasoning.solvers.solver import next_request

from .scenarios import (
    COMPLEX_SRG_BOTH_OUTCOMES,
    COMPLEX_SRG_O1,
    COMPLEX_SRG_O2,
    make_complex_srg,
)
from .utils import SolverScenario, asked

pytestmark = pytest.mark.unit

SCENARIOS = [
    pytest.param(COMPLEX_SRG_O1, id="o1_only"),
    pytest.param(COMPLEX_SRG_O2, id="o2_only"),
    pytest.param(COMPLEX_SRG_BOTH_OUTCOMES, id="both_outcomes"),
]

TRACE_APIS = [
    ("reasoning_trace", lambda e: reasoning_trace(e)),
    ("outcomes", lambda e: outcomes(e)),
    ("explain", lambda e: reasoning_trace(e).outcome_paths),
    (
        "explain_outcome",
        lambda e: [p for p in reasoning_trace(e).outcome_paths if p.outcome_id == "O1"],
    ),
    ("has_outcome", lambda e: ("O1" in {o.id for o in outcomes(e)})),
    ("get_outcome_paths", lambda e: _outcome_paths(e)),
    ("get_all_distinct_paths", lambda e: _all_distinct_paths(e)),
]


def all_false_srg() -> tuple[SRG, list[str]]:
    """Root -> [all(P1,P2,P3)] -> DENIED on False."""
    srg = SRGBuilder()
    pred_ids = [srg.add_predicate(f"q{i}") for i in range(3)]
    outcome_id = srg.add_outcome("DENIED")
    agg_id = srg.add_aggregator(AllStrategy(), True, pred_ids, name="reqs")
    agg_node = srg.add_node(agg_id)
    outcome_node = srg.add_node(outcome_id)
    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, outcome_node, condition=False)
    return srg.build(), pred_ids


class TestFrontierAgreesWithSolver:
    """``is_resolved`` must mean exactly what the solver means by "done"."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", SCENARIOS)
    async def test_resolved_exactly_when_solver_finishes(
        self, scenario: SolverScenario
    ) -> None:
        execution = SRGExecution(srg=make_complex_srg())
        request = next_request(execution)

        for step in scenario.steps:
            assert request is not None
            # While the solver still has questions, the execution is unresolved.
            assert not is_resolved(execution)
            execution = apply_answers(
                execution,
                {
                    r.predicate.id: Answer(is_met=v, reasoning="r")
                    for r, v in zip(
                        request.predicate_requests, step.answers, strict=True
                    )
                },
            )
            request = next_request(execution)

        assert request is None
        assert is_resolved(execution)
        assert asked(execution) == []

    def test_siblings_are_reported_left_to_right(self) -> None:
        """Two branches open at once follow the order the solver takes them."""
        srg = SRGBuilder()
        gate = srg.add_predicate("gate")
        gate_node = srg.add_node(srg.add_aggregator(AllStrategy(), True, [gate]))
        srg.add_edge("Root", gate_node, condition=True)

        first = srg.add_predicate("first branch")
        second = srg.add_predicate("second branch")
        for pred_id in (first, second):
            branch_node = srg.add_node(
                srg.add_aggregator(AllStrategy(), True, [pred_id])
            )
            srg.add_edge(gate_node, branch_node, condition=True)

        execution = SRGExecution(
            srg=srg.build(), answers={gate: Answer(is_met=True, reasoning="r")}
        )

        assert asked(execution) == [first, second]

    def test_a_node_id_answers_for_the_item_it_wraps(self) -> None:
        """A node id answers for the item it wraps."""
        srg = SRGBuilder()
        pred_id = srg.add_predicate("question")
        node_id = srg.add_node(srg.add_aggregator(AllStrategy(), True, [pred_id]))
        execution = SRGExecution(srg=srg.build())

        assert [p.id for p in _next_needed_predicates(execution, node_id)] == [pred_id]


class TestShortCircuitCountsAsResolved:
    """Resolved means "nothing left to ask", not "every predicate answered"."""

    def test_short_circuited_execution_is_resolved(self) -> None:
        srg, pred_ids = all_false_srg()
        execution = SRGExecution(
            srg=srg, answers={pred_ids[0]: Answer(is_met=False, reasoning="r")}
        )

        assert is_resolved(execution)
        assert len(execution.answers) < len(pred_ids)
        assert [o.description for o in outcomes(execution)] == ["DENIED"]

    def test_undetermined_execution_is_not_resolved(self) -> None:
        srg, pred_ids = all_false_srg()
        execution = SRGExecution(
            srg=srg, answers={pred_ids[0]: Answer(is_met=True, reasoning="r")}
        )

        assert not is_resolved(execution)
        assert asked(execution) == [pred_ids[1]]

    def test_frontier_excludes_untaken_branches(self) -> None:
        """Predicates behind an edge the policy does not follow are not needed."""
        srg = SRGBuilder()
        gate = srg.add_predicate("gate")
        behind = srg.add_predicate("behind the True edge")
        outcome_id = srg.add_outcome("REACHED")
        gate_node = srg.add_node(gate)
        behind_node = srg.add_node(behind)
        outcome_node = srg.add_node(outcome_id)
        srg.add_edge("Root", gate_node, condition=True)
        srg.add_edge(gate_node, behind_node, condition=True)
        srg.add_edge(behind_node, outcome_node, condition=True)

        # gate=False: the True edge is not taken, so `behind` is never needed.
        execution = SRGExecution(
            srg=srg.build(), answers={gate: Answer(is_met=False, reasoning="r")}
        )
        assert is_resolved(execution)
        assert outcomes(execution) == []

        # gate=True: the branch is entered, so `behind` becomes outstanding.
        execution = SRGExecution(
            srg=srg.build(), answers={gate: Answer(is_met=True, reasoning="r")}
        )
        assert not is_resolved(execution)
        assert asked(execution) == [behind]


class TestUnresolvedBlocksInterpretation:
    """Every interpretation API refuses an unresolved execution - uniformly."""

    @pytest.mark.parametrize("name,call", TRACE_APIS, ids=[n for n, _ in TRACE_APIS])
    def test_api_raises_when_unresolved(
        self, name: str, call: Callable[[SRGExecution], Any]
    ) -> None:
        srg, pred_ids = all_false_srg()
        execution = SRGExecution(
            srg=srg, answers={pred_ids[0]: Answer(is_met=True, reasoning="r")}
        )

        with pytest.raises(ExecutionNotResolvedError, match="not resolved"):
            call(execution)

    def test_error_names_an_outstanding_predicate(self) -> None:
        srg, pred_ids = all_false_srg()
        execution = SRGExecution(
            srg=srg, answers={pred_ids[0]: Answer(is_met=True, reasoning="r")}
        )

        with pytest.raises(ExecutionNotResolvedError, match=pred_ids[1]):
            outcomes(execution)

    def test_bare_predicate_node_is_covered_by_the_same_guard(self) -> None:
        """The old shape-dependent ValueError is subsumed, not special-cased."""
        srg = SRGBuilder()
        pred_id = srg.add_predicate("q")
        outcome_id = srg.add_outcome("REACHED")
        pred_node = srg.add_node(pred_id)
        outcome_node = srg.add_node(outcome_id)
        srg.add_edge("Root", pred_node, condition=True)
        srg.add_edge(pred_node, outcome_node, condition=True)

        with pytest.raises(ExecutionNotResolvedError, match="not resolved"):
            outcomes(SRGExecution(srg=srg.build()))


class TestResolvedIsStableUnderBackfill:
    """Adding answers to a resolved execution cannot un-resolve it."""

    def test_backfilling_every_predicate_keeps_it_resolved(self) -> None:
        srg, pred_ids = all_false_srg()
        execution = SRGExecution(
            srg=srg, answers={pred_ids[0]: Answer(is_met=False, reasoning="r")}
        )
        assert is_resolved(execution)
        before = [o.description for o in outcomes(execution)]

        for is_met in (True, False):
            backfilled = SRGExecution(
                srg=srg,
                answers={
                    # Existing answers win: this adds answers, it does not revise them.
                    **{p: Answer(is_met=is_met, reasoning="r") for p in pred_ids},
                    **execution.answers,
                },
            )
            assert len(backfilled.answers) == len(pred_ids)
            assert is_resolved(backfilled)
            assert [o.description for o in outcomes(backfilled)] == before

    @pytest.mark.asyncio
    async def test_backfill_preserves_resolution_on_complex_graph(self) -> None:
        scenario = COMPLEX_SRG_BOTH_OUTCOMES
        srg = make_complex_srg()
        execution = SRGExecution(srg=srg)
        request = next_request(execution)
        for step in scenario.steps:
            assert request is not None
            execution = apply_answers(
                execution,
                {
                    r.predicate.id: Answer(is_met=v, reasoning="r")
                    for r, v in zip(
                        request.predicate_requests, step.answers, strict=True
                    )
                },
            )
            request = next_request(execution)
        assert is_resolved(execution)
        before = sorted(o.description for o in outcomes(execution))

        backfilled = SRGExecution(
            srg=srg,
            answers={
                **{
                    pred_id: Answer(is_met=False, reasoning="backfill")
                    for pred_id in srg.predicates
                },
                **execution.answers,
            },
        )
        assert is_resolved(backfilled)
        assert sorted(o.description for o in outcomes(backfilled)) == before
