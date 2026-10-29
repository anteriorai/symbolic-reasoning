"""Oracle context belongs to graph branches, independently of batching."""

from pathlib import Path

import pytest

from symbolic_reasoning import (
    Answer,
    Coverage,
    OracleRequest,
    SRGBuilder,
    SRGExecution,
    TraceStep,
    apply_answers,
    compile_srg_file,
    is_resolved,
    next_request,
    reasoning_trace,
)
from symbolic_reasoning.models import AllStrategy
from symbolic_reasoning.solvers.requests import build_request

from .scenarios import COMPLEX_SRG_O1, make_complex_srg
from .utils import asked


def context_ids(request: OracleRequest) -> dict[str, list[str]]:
    return {
        r.predicate.id: [s.predicate_id for s in r.contextual_predicates]
        for r in request.predicate_requests
    }


def test_complex_siblings_and_descendants_have_separate_contexts() -> None:
    execution = SRGExecution(srg=make_complex_srg())
    expected = [
        {"P1": [], "P12": []},
        {"P5": ["P1"], "P13": ["P12"]},
        {"P6": ["P1", "P5"], "P14": ["P12", "P13"]},
        {"P11": ["P12", "P13", "P14"], "P9": ["P1", "P5", "P6"]},
        {"P15": ["P12", "P13", "P14", "P11"], "P10": ["P1", "P5", "P6", "P9"]},
    ]
    request = next_request(execution)
    for step, contexts in zip(COMPLEX_SRG_O1.steps, expected, strict=True):
        assert request is not None
        assert context_ids(request) == contexts
        execution = apply_answers(
            execution,
            {
                r.predicate.id: Answer(is_met=v, reasoning="r")
                for r, v in zip(request.predicate_requests, step.answers, strict=True)
            },
        )
        request = next_request(execution)
    assert request is None


@pytest.mark.parametrize("shared_node", [False, True])
@pytest.mark.parametrize("b_answer", [False, True])
def test_shared_fact_preserves_reachable_contexts(
    shared_node: bool, b_answer: bool
) -> None:
    """Root -> A/B -> C -> D, with C shared as a symbol or as a graph node."""
    srg = SRGBuilder()
    a, b, c, d = [srg.add_predicate(q) for q in "ABCD"]
    a_node, b_node, c_node, d_node = [srg.add_node(p) for p in (a, b, c, d)]
    other_c = c_node if shared_node else srg.add_node(c)
    srg.add_edge("Root", a_node).add_edge("Root", b_node)
    srg.add_edge(a_node, c_node).add_edge(b_node, other_c)
    srg.add_edge(c_node, d_node)
    if not shared_node:
        srg.add_edge(other_c, d_node)

    execution = SRGExecution(srg=srg.build())
    request = next_request(execution)
    assert request is not None
    execution = apply_answers(
        execution,
        {
            a: Answer(is_met=True, reasoning="r"),
            b: Answer(is_met=b_answer, reasoning="r"),
        },
    )
    request = next_request(execution)
    assert request is not None
    assert asked(execution) == [c]
    assert context_ids(request) == {c: [a, b] if b_answer else [a]}
    # Context reconstruction survives serialization and ignores answer insertion order.
    execution = SRGExecution.model_validate_json(execution.model_dump_json())
    execution = SRGExecution(
        srg=execution.srg, answers=dict(reversed(list(execution.answers.items())))
    )
    assert next_request(execution) == request
    assert build_request(execution) == request
    assert OracleRequest.model_validate_json(request.model_dump_json()) == request

    execution = apply_answers(
        execution,
        {
            r.predicate.id: Answer(is_met=True, reasoning="r")
            for r in request.predicate_requests
        },
    )
    request = next_request(execution)
    assert request is not None
    assert asked(execution) == [d]
    assert set(context_ids(request)[d]) == ({a, b, c} if b_answer else {a, c})
    execution = apply_answers(
        execution,
        {
            r.predicate.id: Answer(is_met=True, reasoning="r")
            for r in request.predicate_requests
        },
    )
    assert next_request(execution) is None


@pytest.mark.parametrize("coverage", list(Coverage))
def test_cached_answers_and_duplicate_contexts(coverage: Coverage) -> None:
    """Two sibling occurrences of the same aggregator need one identical context."""
    srg = SRGBuilder()
    a, b = [srg.add_predicate(q) for q in "AB"]
    agg = srg.add_aggregator(AllStrategy(), True, [a, b])
    for _ in range(2):
        srg.add_edge("Root", srg.add_node(agg))
    execution = SRGExecution(srg=srg.build())
    cached_answer = Answer(is_met=coverage is Coverage.MINIMAL, reasoning="Cached fact")
    execution = apply_answers(execution, {a: cached_answer})
    request = next_request(execution, coverage)
    assert request is not None
    assert context_ids(request) == {b: [a]}
    # Extra coverage must not make an already decided execution unresolved.
    assert is_resolved(execution) is (coverage is Coverage.REACHABLE)
    assert asked(execution) == ([] if coverage is Coverage.REACHABLE else [b])
    assert request.predicate_requests[0].contextual_predicates == [
        TraceStep(predicate_id=a, is_met=cached_answer.is_met)
    ]
    assert request.predicates == {a: srg.predicates[a]}
    assert request.answers == {a: cached_answer}
    execution = apply_answers(
        execution,
        {
            r.predicate.id: Answer(is_met=True, reasoning="r")
            for r in request.predicate_requests
        },
    )
    assert next_request(execution, coverage) is None


def test_repeated_convergence_includes_longer_paths() -> None:
    """A direct path and 4096 layered paths merge before an unanswered descendant."""
    srg = SRGBuilder()
    previous = ["Root"]
    known = []
    for layer in range(12):
        current = []
        for side in range(2):
            predicate_id = srg.add_predicate(f"{layer}/{side}")
            known.append(predicate_id)
            node_id = srg.add_node(predicate_id)
            for parent in previous:
                srg.add_edge(parent, node_id)
            current.append(node_id)
        previous = current

    merge = srg.add_predicate("Merge")
    known.append(merge)
    merge_node = srg.add_node(merge)
    # BFS encounters this node before the longer paths have supplied their context.
    for parent in ["Root", *previous]:
        srg.add_edge(parent, merge_node)
    pending = srg.add_predicate("Pending")
    srg.add_edge(merge_node, srg.add_node(pending))
    execution = SRGExecution(
        srg=srg.build(),
        answers={p: Answer(is_met=True, reasoning="known") for p in known},
    )

    built = build_request(execution)
    assert built is not None
    contextual_ids = [
        s.predicate_id for s in built.predicate_requests[0].contextual_predicates
    ]
    assert set(contextual_ids) == set(known)
    assert len(contextual_ids) == len(known)
    assert asked(execution) == [pending]
    request = next_request(execution)
    assert request is not None
    assert request == built
    execution = apply_answers(
        execution,
        {
            r.predicate.id: Answer(is_met=True, reasoning="r")
            for r in request.predicate_requests
        },
    )
    assert next_request(execution) is None


def test_requests_list_each_answer_once_and_traces_only_reference_them() -> None:
    policy = Path(__file__).parent.parent / "examples/data/msk-review/policy.srg"
    execution = SRGExecution(srg=compile_srg_file(policy))
    requests = []
    while (request := next_request(execution, Coverage.REACHABLE)) is not None:
        requests.append(request)
        execution = apply_answers(
            execution,
            {
                r.predicate.id: Answer(
                    is_met=True, reasoning=f"Evidence {r.predicate.id}."
                )
                for r in request.predicate_requests
            },
        )
    assert any(r.answers for r in requests)
    trace = reasoning_trace(execution).model_dump_json()
    for predicate_id in execution.answers:
        question = execution.srg.predicates[predicate_id].question
        for request in requests:
            dumped = request.model_dump_json()
            assert dumped.count(f"Evidence {predicate_id}.") <= 1
            assert dumped.count(question) <= 1
        assert f"Evidence {predicate_id}." not in trace
        assert question not in trace


def test_unhydrated_requests_reference_context_only_by_id() -> None:
    execution = apply_answers(
        SRGExecution(srg=make_complex_srg()),
        {p: Answer(is_met=True, reasoning="r") for p in ["P1", "P12"]},
    )

    hydrated = next_request(execution)
    bare = next_request(execution, hydrate_context=False)

    assert hydrated is not None and bare is not None
    assert set(hydrated.predicates) == set(hydrated.answers) == {"P1", "P12"}
    assert bare.predicates == bare.answers == {}
    assert bare.predicate_requests == hydrated.predicate_requests
