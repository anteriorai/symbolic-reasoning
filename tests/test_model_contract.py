"""Runtime values use fixed library types and keep schema-defined graph annotations."""

import pytest

import symbolic_reasoning
from symbolic_reasoning import (
    Answer,
    OracleRequest,
    Predicate,
    SRGBuilder,
    SRGExecution,
    SRGValidationError,
    apply_answers,
    asolve,
    compile_srg_string,
    load_srg,
    next_request,
    outcomes,
)
from symbolic_reasoning.gen.py.srg import Citation
from symbolic_reasoning.models import Outcome


def test_graph_annotations_round_trip_through_builder_and_json() -> None:
    draft = SRGBuilder()
    predicate_id = draft.add_predicate(
        "Covered?", label="Coverage", citation_ids=["policy"]
    )
    draft.citations = {"policy": Citation(source_ref="policy.pdf")}
    outcome_id = draft.add_outcome("Approved", doc="All requirements met")
    node = draft.add_node(predicate_id)
    draft.add_edge("Root", node).add_edge(node, draft.add_node(outcome_id))
    original = draft.build()
    edited = SRGBuilder.from_srg(original)
    edited.predicates[predicate_id] = Predicate(id=predicate_id, question="Updated?")

    assert original.predicates[predicate_id].question == "Covered?"
    assert edited.build().predicates[predicate_id].question == "Updated?"
    loaded = load_srg(original.model_dump_json())
    assert type(loaded.predicates[predicate_id]) is Predicate
    assert loaded.predicates[predicate_id].citation_ids == ["policy"]
    assert loaded.outcomes[outcome_id].doc == "All requirements met"


@pytest.mark.asyncio
async def test_language_metadata_remains_data_in_requests_and_traces() -> None:
    srg = compile_srg_string("""
predicate p: "Covered?"
  metadata: { priority: 1 }
predicate q: "Signed?"
outcome yes: "Approved"
  metadata: { code: "A1" }
path approve: p => q => yes
""")
    partial = apply_answers(
        SRGExecution(srg=srg), {"p": Answer(is_met=True, reasoning="Confirmed")}
    )
    request = next_request(partial)
    assert request is not None
    assert type(request.predicates["p"]) is Predicate
    assert request.predicates["p"].metadata == {"priority": 1}
    assert type(request.answers["p"]) is Answer

    def oracle(request: OracleRequest) -> dict[str, Answer]:
        return {
            r.predicate.id: Answer(is_met=True, reasoning="Confirmed")
            for r in request.predicate_requests
        }

    [reached] = outcomes(await asolve(partial, oracle))
    assert type(reached) is Outcome
    assert reached.metadata == {"code": "A1"}


@pytest.mark.parametrize("symbols", ["predicates", "outcomes"])
def test_graphs_reject_fields_outside_the_schema(symbols: str) -> None:
    graph = compile_srg_string(
        'predicate p: "Covered?"\noutcome yes: "Approved"\npath approve: p => yes'
    ).model_dump(mode="json")
    next(iter(graph[symbols].values()))["priority"] = 1
    with pytest.raises(SRGValidationError, match="extra_forbidden"):
        load_srg(graph)


def test_star_import_exposes_only_the_public_api() -> None:
    namespace: dict[str, object] = {}
    exec("from symbolic_reasoning import *", namespace)
    namespace.pop("__builtins__")
    assert sorted(namespace) == sorted(symbolic_reasoning.__all__)
    assert "Path" not in namespace
