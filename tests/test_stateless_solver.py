"""Requests and answer application have no hidden solver state."""

import json
from types import MappingProxyType

import pytest

from symbolic_reasoning import SRGBuilder, apply_answers
from symbolic_reasoning.models import SRG, AllStrategy, Answer, Coverage, SRGExecution
from symbolic_reasoning.solvers.solver import next_request

pytestmark = pytest.mark.unit


def chain_srg() -> tuple[SRG, list[str]]:
    """Root -> [all(P1,P2,P3)] -> APPROVED when all three are met."""
    srg = SRGBuilder()
    pred_ids = [srg.add_predicate(f"P{i + 1}?") for i in range(3)]
    outcome_id = srg.add_outcome("APPROVED")
    agg_id = srg.add_aggregator(AllStrategy(), True, pred_ids, name="reqs")
    agg_node = srg.add_node(agg_id)
    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, srg.add_node(outcome_id), condition=True)
    return srg.build(), pred_ids


class TestNoHiddenState:
    def test_next_request_does_not_mutate_execution(self) -> None:
        """next_request only reads execution.answers - it never writes to it."""
        srg, _ = chain_srg()
        execution = SRGExecution(srg=srg)

        next_request(execution)

        assert execution.answers == {}

    def test_next_request_is_deterministic(self) -> None:
        """Same execution in, same request out - nothing is cached or consumed
        between calls, so calling it again is safe."""
        srg, _ = chain_srg()
        execution = SRGExecution(srg=srg)

        assert next_request(execution) == next_request(execution)

    def test_accumulating_answers_does_not_mutate_the_original(self) -> None:
        srg, pred_ids = chain_srg()
        execution = SRGExecution(srg=srg)
        request = next_request(execution)
        assert request is not None

        updated = apply_answers(
            execution,
            {
                r.predicate.id: Answer(is_met=True, reasoning="y")
                for r in request.predicate_requests
            },
        )

        assert execution.answers == {}
        assert set(updated.answers) == {pred_ids[0]}
        assert updated is not execution


class TestResumeFromAHandBuiltExecution:
    def test_resumes_mid_solve_without_a_solver_object(self) -> None:
        """A solve can pick up from an execution built directly from answers,
        with no solver/session object involved at all."""
        srg, pred_ids = chain_srg()
        execution = SRGExecution(
            srg=srg,
            answers={
                pred_ids[0]: Answer(is_met=True, reasoning="y"),
                pred_ids[1]: Answer(is_met=True, reasoning="y"),
            },
        )

        request = next_request(execution)

        assert request is not None
        assert [p.predicate.id for p in request.predicate_requests] == [pred_ids[2]]
        assert {
            s.predicate_id for s in request.predicate_requests[0].contextual_predicates
        } == {
            pred_ids[0],
            pred_ids[1],
        }

    def test_survives_a_serialization_round_trip(self) -> None:
        srg, pred_ids = chain_srg()
        execution = SRGExecution(srg=srg)
        request = next_request(execution)
        assert request is not None
        execution = apply_answers(
            execution,
            {
                r.predicate.id: Answer(is_met=True, reasoning="y")
                for r in request.predicate_requests
            },
        )

        reloaded = SRGExecution.model_validate_json(execution.model_dump_json())

        request = next_request(reloaded)
        assert request == next_request(execution)
        assert request is not None
        assert [p.predicate.id for p in request.predicate_requests] == [pred_ids[1]]


@pytest.mark.parametrize("coverage", [Coverage.MINIMAL, Coverage.REACHABLE])
def test_resume_preserves_explicit_coverage(coverage: Coverage) -> None:
    """Persist scheduling configuration alongside the graph and known answers."""
    srg, pred_ids = chain_srg()
    execution = SRGExecution(
        srg=srg, answers={pred_ids[0]: Answer(is_met=False, reasoning="Failed")}
    )
    checkpoint = json.dumps(
        {
            "execution": execution.model_dump(mode="json"),
            "coverage": coverage.value,
        }
    )
    loaded = json.loads(checkpoint)
    restored = SRGExecution.model_validate(loaded["execution"])
    restored_coverage = Coverage(loaded["coverage"])

    request = next_request(restored, restored_coverage)
    assert request == next_request(execution, coverage)
    if coverage == Coverage.MINIMAL:
        assert request is None
    else:
        assert request is not None
        assert [r.predicate.id for r in request.predicate_requests] == [pred_ids[1]]
    # Coverage can change on the same snapshot without changing its answers.
    assert next_request(restored, Coverage.MINIMAL) is None
    assert next_request(restored, Coverage.REACHABLE) is not None
    assert restored.answers == execution.answers


class TestAnswersAccumulate:
    """Answers are facts keyed by predicate ID, not a transaction per request."""

    def two_open_predicates(self) -> tuple[SRGExecution, list[str]]:
        srg = SRGBuilder()
        a, b = (srg.add_predicate(q) for q in "AB")
        for predicate_id in (a, b):
            srg.add_edge("Root", srg.add_node(predicate_id))
        return SRGExecution(srg=srg.build()), [a, b]

    def test_answering_part_of_a_request_leaves_the_rest_outstanding(self) -> None:
        execution, (a, b) = self.two_open_predicates()
        request = next_request(execution)
        assert request is not None
        assert {r.predicate.id for r in request.predicate_requests} == {a, b}

        execution = apply_answers(execution, {a: Answer(is_met=True, reasoning="a")})

        request = next_request(execution)
        assert request is not None
        assert [r.predicate.id for r in request.predicate_requests] == [b]

    def test_an_answer_for_an_unknown_predicate_is_rejected(self) -> None:
        execution, (a, _) = self.two_open_predicates()

        with pytest.raises(ValueError, match="not in the SRG"):
            apply_answers(
                execution,
                {
                    a: Answer(is_met=True, reasoning="a"),
                    "ghost": Answer(is_met=True, reasoning="?"),
                },
            )
        assert execution.answers == {}

    def test_correction_preserves_other_answers_and_changes_the_frontier(self) -> None:
        srg, (a, b, c) = chain_srg()
        original = SRGExecution(
            srg=srg,
            answers={
                a: Answer(is_met=True, reasoning="Known"),
                b: Answer(is_met=False, reasoning="Initial"),
            },
        )
        assert next_request(original) is None

        updated = apply_answers(
            original, {b: Answer(is_met=True, reasoning="Corrected")}
        )

        assert updated.answers[a] == original.answers[a]
        assert not original.answers[b].is_met
        assert updated.answers[b].reasoning == "Corrected"
        request = next_request(updated)
        assert request is not None
        assert [r.predicate.id for r in request.predicate_requests] == [c]

    def test_read_only_mapping_is_accepted_without_mutation(self) -> None:
        execution, (a, _) = self.two_open_predicates()

        answer = Answer(is_met=True, reasoning="Evidence")
        submission = MappingProxyType({a: answer})
        updated = apply_answers(execution, submission)

        assert updated.answers[a].model_dump() == answer.model_dump()
        assert submission[a] is answer
        assert execution.answers == {}
        assert updated.srg is execution.srg

    def test_empty_submission_preserves_state_without_requiring_progress(self) -> None:
        execution, (a, _) = self.two_open_predicates()
        execution = apply_answers(
            execution, {a: Answer(is_met=True, reasoning="Known")}
        )
        updated = apply_answers(execution, {})

        assert updated is not execution
        assert updated.answers is not execution.answers
        assert updated.model_dump() == execution.model_dump()
        assert next_request(updated) == next_request(execution)
