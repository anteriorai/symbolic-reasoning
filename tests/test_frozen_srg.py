"""A built SRG is validated and read-only; edits go through SRGBuilder."""

import json

import pytest
from pydantic import ValidationError

from symbolic_reasoning import (
    SRG,
    SRGBuilder,
    SRGExecution,
    SRGValidationError,
    compile_srg_string,
    load_srg,
)
from symbolic_reasoning.models import AtLeastStrategy

pytestmark = pytest.mark.unit

SOURCE = 'predicate adult: "Is the applicant an adult?"\noutcome ok: "Approved"\npath approve: adult => ok'


def test_graph_and_its_symbols_cannot_be_reassigned() -> None:
    srg = compile_srg_string(SOURCE)
    with pytest.raises(ValidationError):
        srg.policy_context = "Changed"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        srg.predicates["adult"].question = "Changed"  # ty: ignore[invalid-assignment]
    edge = next(iter(srg.edges.values()))
    with pytest.raises(ValidationError):
        edge.condition = False  # ty: ignore[invalid-assignment]


def test_strategy_cannot_be_retagged() -> None:
    builder = SRGBuilder()
    predicate = builder.add_predicate("Q")
    aggregator = builder.add_aggregator(AtLeastStrategy(count=1), True, [predicate])
    strategy = builder.build().aggregators[aggregator].strategy.root
    assert isinstance(strategy, AtLeastStrategy)
    with pytest.raises(ValidationError):
        strategy.count = 0  # ty: ignore[invalid-assignment]


def test_builder_edits_do_not_reach_built_graphs() -> None:
    srg = compile_srg_string(SOURCE)
    builder = SRGBuilder.from_srg(srg)
    builder.add_predicate("Another question")

    assert len(builder.build().predicates) == 2
    assert len(srg.predicates) == 1


def test_build_validates_structure() -> None:
    builder = SRGBuilder()
    builder.add_edge("Root", builder.add_node(builder.add_predicate("Q")))
    builder.nodes["SN_9"] = builder.nodes["Root"].model_copy(
        update={"id": "SN_9", "item_id": "missing"}
    )
    with pytest.raises(SRGValidationError, match="unknown symbol 'missing'"):
        builder.build()


def test_loading_validates_structure() -> None:
    data = compile_srg_string(SOURCE).model_dump(mode="json")
    data["edges"]["dangling"] = {"source": "Root", "target": "SN_99", "condition": True}
    message = "Edge 'dangling' target refers to unknown graph node 'SN_99'"
    with pytest.raises(SRGValidationError) as error:
        load_srg(data)
    assert str(error.value) == message
    with pytest.raises(ValidationError, match=message):
        SRG.model_validate(data)


def test_loading_reports_invalid_fields_as_library_errors() -> None:
    data = compile_srg_string(SOURCE).model_dump(mode="json")
    data["predicates"]["adult"]["question"] = 7
    with pytest.raises(SRGValidationError, match="question"):
        load_srg(json.dumps(data))


def test_existing_graphs_are_revalidated() -> None:
    # model_copy skips validation, so this graph never passed validate_srg.
    unchecked = compile_srg_string(SOURCE).model_copy(update={"nodes": {}})

    with pytest.raises(ValidationError, match="missing its Root node"):
        SRGExecution(srg=unchecked)


def test_graphs_restored_from_data_are_validated() -> None:
    data = SRGExecution(srg=compile_srg_string(SOURCE)).model_dump(mode="json")
    data["srg"]["nodes"] = {}

    with pytest.raises(ValidationError, match="missing its Root node"):
        SRGExecution.model_validate(data)
