"""Coverage modes: how much of an aggregator a solve answers."""

from collections.abc import Mapping

import pytest

from symbolic_reasoning import (
    SRGBuilder,
    apply_answers,
    compile_srg_string,
    is_resolved,
    outcomes,
    reasoning_trace,
)
from symbolic_reasoning.models import (
    SRG,
    AllStrategy,
    Answer,
    AtLeastStrategy,
    Coverage,
    SRGExecution,
)
from symbolic_reasoning.models.srg_execution import _next_needed_predicates
from symbolic_reasoning.solvers.auto import asolve
from symbolic_reasoning.solvers.protocols import AsyncOracle
from symbolic_reasoning.solvers.requests import OracleRequest
from symbolic_reasoning.solvers.solver import next_request

from .scenarios import make_complex_srg

pytestmark = pytest.mark.unit


def denial_srg() -> tuple[SRG, list[str]]:
    """Root -> [all(q0,q1,q2)] -> DENIED when the requirements are not all met."""
    srg = SRGBuilder()
    pred_ids = [srg.add_predicate(f"q{i}") for i in range(3)]
    outcome_id = srg.add_outcome("DENIED")
    agg_id = srg.add_aggregator(AllStrategy(), True, pred_ids, name="reqs")
    agg_node = srg.add_node(agg_id)
    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, srg.add_node(outcome_id), condition=False)
    return srg.build(), pred_ids


def constant_oracle(is_met: bool) -> AsyncOracle:
    """An oracle that answers every predicate the same way."""

    async def oracle(request: OracleRequest) -> Mapping[str, Answer]:
        return {
            r.predicate.id: Answer(is_met=is_met, reasoning="r")
            for r in request.predicate_requests
        }

    return oracle


async def drive(srg: SRG, is_met: bool, coverage: Coverage) -> list[list[str]]:
    """Solve, answering every predicate the same way. Returns predicates per round."""
    execution = SRGExecution(srg=srg)
    rounds = []
    request = next_request(execution, coverage)
    while request is not None:
        rounds.append([p.predicate.id for p in request.predicate_requests])
        execution = apply_answers(
            execution,
            {
                r.predicate.id: Answer(is_met=is_met, reasoning="r")
                for r in request.predicate_requests
            },
        )
        request = next_request(execution, coverage)
    return rounds


class TestMinimalIsTheDefault:
    @pytest.mark.asyncio
    async def test_minimal_stops_at_the_first_failure(self) -> None:
        srg, pred_ids = denial_srg()

        execution = SRGExecution(srg=srg)
        assert next_request(execution) == next_request(execution, Coverage.MINIMAL)
        assert await drive(srg, is_met=False, coverage=Coverage.MINIMAL) == [
            [pred_ids[0]]
        ]


class TestReachableAnswersEveryPredicateItReaches:
    @pytest.mark.asyncio
    async def test_reachable_asks_the_rest_of_the_aggregator(self) -> None:
        """Keeps going past the short-circuit, still one predicate per round."""
        srg, pred_ids = denial_srg()

        rounds = await drive(srg, is_met=False, coverage=Coverage.REACHABLE)

        assert rounds == [[pred_id] for pred_id in pred_ids]

    @pytest.mark.asyncio
    async def test_reachable_enters_an_already_decided_aggregator(self) -> None:
        """A nested aggregator that short-circuited still gets drained.

        Skipping arguments whose verdict is known - as MINIMAL does - would
        strand ``inner``'s second predicate here, since ``inner`` is already
        False once its first argument is.
        """
        srg = SRGBuilder()
        inner_preds = [srg.add_predicate(f"inner{i}") for i in range(2)]
        tail = srg.add_predicate("tail")
        inner = srg.add_aggregator(AllStrategy(), True, inner_preds, name="inner")
        outer = srg.add_aggregator(AllStrategy(), True, [inner, tail], name="outer")
        outcome_id = srg.add_outcome("DENIED")
        outer_node = srg.add_node(outer)
        srg.add_edge("Root", outer_node, condition=True)
        srg.add_edge(outer_node, srg.add_node(outcome_id), condition=False)

        minimal = await asolve(
            srg.build(), constant_oracle(False), coverage=Coverage.MINIMAL
        )
        reachable = await asolve(
            srg.build(), constant_oracle(False), coverage=Coverage.REACHABLE
        )

        assert set(minimal.answers) == {inner_preds[0]}
        assert set(reachable.answers) == {*inner_preds, tail}

    @pytest.mark.asyncio
    async def test_reachable_reports_every_unmet_requirement(self) -> None:
        """All reasons, not just the first, and the same verdict."""
        srg, pred_ids = denial_srg()

        minimal = await asolve(srg, constant_oracle(False), coverage=Coverage.MINIMAL)
        reachable = await asolve(
            srg, constant_oracle(False), coverage=Coverage.REACHABLE
        )

        assert [o.description for o in outcomes(minimal)] == ["DENIED"]
        assert [o.description for o in outcomes(reachable)] == ["DENIED"]
        assert [
            s.predicate_id for s in reasoning_trace(minimal).outcome_paths[0].steps
        ] == [pred_ids[0]]
        assert [
            s.predicate_id for s in reasoning_trace(reachable).outcome_paths[0].steps
        ] == pred_ids

    @pytest.mark.asyncio
    async def test_reachable_terminates_on_a_complex_graph(self) -> None:
        """Every round must make progress: a predicate already answered is never
        handed back, or the serial walk would never finish."""
        srg = make_complex_srg()

        minimal = await asolve(srg, constant_oracle(True), coverage=Coverage.MINIMAL)
        reachable = await asolve(
            srg, constant_oracle(True), coverage=Coverage.REACHABLE
        )

        assert is_resolved(reachable)
        assert set(reachable.answers) > set(minimal.answers)


class TestCoverageIsReachabilityBounded:
    @pytest.mark.asyncio
    async def test_reachable_does_not_enter_untaken_branches(self) -> None:
        """REACHABLE must not manufacture outcomes behind a condition that failed."""
        srg = SRGBuilder()
        gate = srg.add_predicate("gate")
        behind = srg.add_predicate("behind the True edge")
        outcome_id = srg.add_outcome("REACHED")
        gate_node = srg.add_node(gate)
        behind_node = srg.add_node(behind)
        srg.add_edge("Root", gate_node, condition=True)
        srg.add_edge(gate_node, behind_node, condition=True)
        srg.add_edge(behind_node, srg.add_node(outcome_id), condition=True)

        execution = await asolve(
            srg.build(), constant_oracle(False), coverage=Coverage.REACHABLE
        )

        # The gate failed, so nothing behind the True edge is ever asked.
        assert set(execution.answers) == {gate}
        assert outcomes(execution) == []


class TestCoverageIsSound:
    """MINIMAL and REACHABLE differ in what they ask, never in what they conclude."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_met", [True, False])
    async def test_coverage_does_not_change_the_verdict(self, is_met: bool) -> None:
        for srg in (denial_srg()[0], make_complex_srg()):
            minimal = await asolve(
                srg, constant_oracle(is_met), coverage=Coverage.MINIMAL
            )
            reachable = await asolve(
                srg, constant_oracle(is_met), coverage=Coverage.REACHABLE
            )

            assert [o.description for o in outcomes(reachable)] == [
                o.description for o in outcomes(minimal)
            ]
            # REACHABLE only ever adds answers to what deciding required.
            assert set(minimal.answers) <= set(reachable.answers)

    @pytest.mark.asyncio
    async def test_answers_are_attributed_to_the_right_outcome(self) -> None:
        """Coverage is graph-wide, but explain() still separates branches."""
        srg = SRGBuilder()
        left = [srg.add_predicate(f"L{i}") for i in range(3)]
        right = [srg.add_predicate(f"R{i}") for i in range(3)]
        left_outcome = srg.add_outcome("LEFT_DENIED")
        right_outcome = srg.add_outcome("RIGHT_DENIED")
        left_agg = srg.add_aggregator(AllStrategy(), True, left, name="left")
        right_agg = srg.add_aggregator(AllStrategy(), True, right, name="right")
        left_node, right_node = srg.add_node(left_agg), srg.add_node(right_agg)
        srg.add_edge("Root", left_node, condition=True)
        srg.add_edge("Root", right_node, condition=True)
        srg.add_edge(left_node, srg.add_node(left_outcome), condition=False)
        srg.add_edge(right_node, srg.add_node(right_outcome), condition=False)

        execution = await asolve(
            srg.build(), constant_oracle(False), coverage=Coverage.REACHABLE
        )

        attributed = {
            execution.srg.outcomes[path.outcome_id].description: [
                s.predicate_id for s in path.steps
            ]
            for path in reasoning_trace(execution).outcome_paths
        }
        assert attributed == {"LEFT_DENIED": left, "RIGHT_DENIED": right}


class TestCoverageDoesNotAffectResolution:
    """is_resolved is always judged against MINIMAL - gathering is not solving."""

    def test_short_circuited_execution_is_resolved_despite_unanswered_predicates(
        self,
    ) -> None:
        srg, pred_ids = denial_srg()
        execution = SRGExecution(
            srg=srg, answers={pred_ids[0]: Answer(is_met=False, reasoning="r")}
        )

        assert is_resolved(execution)
        # Two requirements never answered, and interpreting it is still allowed.
        assert set(execution.answers) == {pred_ids[0]}
        reasoning_trace(execution)  # must not raise

    @pytest.mark.asyncio
    async def test_nested_untouched_aggregator_is_found_through_the_subtree(
        self,
    ) -> None:
        srg = SRGBuilder()
        inner_preds = [srg.add_predicate(f"inner{i}") for i in range(2)]
        outer_pred = srg.add_predicate("outer")
        inner = srg.add_aggregator(AllStrategy(), True, inner_preds, name="inner")
        outer = srg.add_aggregator(
            AtLeastStrategy(count=1), True, [outer_pred, inner], name="outer"
        )
        outcome_id = srg.add_outcome("APPROVED")
        outer_node = srg.add_node(outer)
        srg.add_edge("Root", outer_node, condition=True)
        srg.add_edge(outer_node, srg.add_node(outcome_id), condition=True)

        # outer_pred=True satisfies atleast(1); the inner aggregator is never entered.
        execution = SRGExecution(
            srg=srg.build(), answers={outer_pred: Answer(is_met=True, reasoning="r")}
        )

        assert is_resolved(execution)
        assert set(execution.answers) == {outer_pred}

        # REACHABLE reaches them anyway, through the aggregator it never needed.
        reachable = await asolve(
            srg.build(), constant_oracle(True), coverage=Coverage.REACHABLE
        )
        assert set(reachable.answers) == {outer_pred, *inner_preds}


@pytest.mark.parametrize("coverage", list(Coverage))
def test_all_ready_branches_preserve_coverage_and_context(coverage: Coverage) -> None:
    """Root -> all(A,B) --False-> C, alongside Root -> all(D,E)."""
    srg = SRGBuilder()
    a, b, c, d, e = [srg.add_predicate(q) for q in "ABCDE"]
    left = srg.add_node(srg.add_aggregator(AllStrategy(), True, [a, b]))
    right = srg.add_node(srg.add_aggregator(AllStrategy(), True, [d, e]))
    srg.add_edge("Root", left).add_edge("Root", right)
    srg.add_edge(left, srg.add_node(c), condition=False)
    execution = SRGExecution(srg=srg.build())
    expected = (
        [{a: [], d: []}, {e: [d], c: [a]}]
        if coverage is Coverage.MINIMAL
        else [{a: [], d: []}, {b: [a], e: [d]}, {c: [a, b]}]
    )
    for contexts in expected:
        request = next_request(execution, coverage)
        assert request is not None
        assert {
            r.predicate.id: [s.predicate_id for s in r.contextual_predicates]
            for r in request.predicate_requests
        } == contexts
        execution = apply_answers(
            execution,
            {
                r.predicate.id: Answer(is_met=r.predicate.id != a, reasoning="r")
                for r in request.predicate_requests
            },
        )
    assert next_request(execution, coverage) is None


def _two_branch_srg() -> SRG:
    return compile_srg_string(
        'predicate a: "A?"\npredicate b: "B?"\noutcome y: "Y"\npath p: any(a, b) => y\n'
    )


def test_coverage_values_behave_like_their_members() -> None:
    execution = apply_answers(
        SRGExecution(srg=_two_branch_srg()), {"a": Answer(is_met=True, reasoning="")}
    )

    assert next_request(execution, "minimal") == next_request(  # ty: ignore[invalid-argument-type]
        execution, Coverage.MINIMAL
    )
    assert next_request(execution, "reachable") == next_request(  # ty: ignore[invalid-argument-type]
        execution, Coverage.REACHABLE
    )
    assert next_request(execution, "minimal") is None  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("coverage", ["everything", "MINIMAL", None, 1])
def test_unknown_coverage_values_are_rejected(coverage: object) -> None:
    execution = SRGExecution(srg=_two_branch_srg())

    with pytest.raises(ValueError, match="Coverage"):
        next_request(execution, coverage)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="Coverage"):
        _next_needed_predicates(execution, "Root", coverage)  # ty: ignore[invalid-argument-type]


async def test_asolve_rejects_an_unknown_coverage_before_asking() -> None:
    asked: list[str] = []

    async def oracle(request: OracleRequest) -> dict[str, Answer]:
        asked.extend(r.predicate.id for r in request.predicate_requests)
        return {
            r.predicate.id: Answer(is_met=True, reasoning="")
            for r in request.predicate_requests
        }

    with pytest.raises(ValueError, match="Coverage"):
        await asolve(_two_branch_srg(), oracle, coverage="everything")  # ty: ignore[invalid-argument-type]
    assert asked == []
