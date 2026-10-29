"""Validate graph references and cycles before execution, without running a solver."""

import re
from graphlib import CycleError
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from symbolic_reasoning import (
    SRG,
    SRGBuilder,
    SRGValidationError,
    compile_srg_file,
    load_srg,
)
from symbolic_reasoning.models import AllStrategy
from symbolic_reasoning.validation import validate_srg


def assert_rejected(payload: dict[str, Any], message: str) -> None:
    """Loading fails with ``message``, and so does checking the same draft."""
    with pytest.raises(ValidationError, match=re.escape(message)):
        SRG.model_validate(payload)
    with pytest.raises(SRGValidationError) as error:
        validate_srg(SRGBuilder.model_validate(payload))
    assert str(error.value) == message


@pytest.mark.parametrize("name", ["medical-necessity", "underwriting"])
def test_shared_policies_validate_without_mutation(name: str) -> None:
    path = Path(__file__).parents[1] / "examples" / "data" / name / "policy.srg"
    graph = compile_srg_file(path)
    before = graph.model_dump_json()

    validate_srg(graph)

    assert graph.model_dump_json() == before


def test_empty_graph_and_unused_symbols_are_valid() -> None:
    graph = SRGBuilder()
    validate_srg(graph)
    graph.add_predicate("Unused predicate")
    graph.add_outcome("Unreachable outcome")
    validate_srg(graph)


@pytest.fixture
def graph_with_symbols() -> SRG:
    graph = SRGBuilder()
    predicate = graph.add_predicate("Condition")
    graph.add_aggregator(AllStrategy(), True, [predicate])
    graph.add_outcome("Complete")
    return graph.build()


def test_cross_store_symbol_collision_rejected_on_load(
    graph_with_symbols: SRG,
) -> None:
    # Aggregator IDs take a format predicate and outcome IDs cannot, so only
    # a predicate and an outcome can share an ID.
    payload = graph_with_symbols.model_dump(mode="json")
    payload["outcomes"]["P1"] = {**payload["outcomes"]["O1"], "id": "P1"}

    assert_rejected(payload, "Symbol ID 'P1' appears in both predicates and outcomes")


@pytest.mark.parametrize("store", ["predicates", "outcomes"])
@pytest.mark.parametrize("symbol_id", ["A99", "SN_9", "SN9"])
def test_symbol_id_in_a_graph_id_format_rejected_on_load(
    graph_with_symbols: SRG, store: str, symbol_id: str
) -> None:
    payload = graph_with_symbols.model_dump(mode="json")
    symbol = next(iter(payload[store].values()))
    payload[store][symbol_id] = {**symbol, "id": symbol_id}

    assert_rejected(
        payload, f"Symbol ID '{symbol_id}' in {store} is reserved for graph IDs"
    )


# An aggregator cannot take the ID Root: field validation rejects it first.
@pytest.mark.parametrize("store", ["predicates", "outcomes"])
def test_reserved_root_symbol_rejected_on_load(
    graph_with_symbols: SRG, store: str
) -> None:
    payload = graph_with_symbols.model_dump(mode="json")
    symbol = next(iter(payload[store].values()))
    payload[store]["Root"] = {**symbol, "id": "Root"}

    assert_rejected(
        payload, f"Symbol ID 'Root' appears in both reserved Root symbol and {store}"
    )


@pytest.mark.parametrize(
    ("store", "key", "item_id"),
    [
        ("predicates", "P1", "A1"),
        ("aggregators", "A1", "A9"),
        ("outcomes", "O1", "done"),
        ("nodes", "SN_9", "SN_1"),
    ],
)
def test_key_that_differs_from_its_object_id_rejected_on_load(
    graph_with_symbols: SRG, store: str, key: str, item_id: str
) -> None:
    payload = graph_with_symbols.model_dump(mode="json")
    if store == "nodes":
        payload["nodes"][key] = {"id": item_id, "item_id": "P1"}
    else:
        payload[store][key] = {**payload[store][key], "id": item_id}

    assert_rejected(
        payload, f"Key '{key}' in {store} does not match the ID '{item_id}' it holds"
    )


def test_shared_dependencies_and_converging_paths_are_valid() -> None:
    graph = SRGBuilder()
    predicate = graph.add_predicate("Shared condition")
    first = graph.add_aggregator(AllStrategy(), True, [predicate])
    second = graph.add_aggregator(AllStrategy(), False, [first, predicate])
    first_node = graph.add_node(first)
    second_node = graph.add_node(second)
    outcome = graph.add_node(graph.add_outcome("Complete"))
    graph.add_edge("Root", first_node).add_edge("Root", second_node)
    graph.add_edge(first_node, outcome).add_edge(second_node, outcome)

    validate_srg(graph)


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("missing", "Graph is missing its Root node"),
        ("wrong_id", "Root node must have id 'Root'; got 'SN1'"),
        ("wrong_item", "Root node must have item_id 'Root'; got 'P1'"),
    ],
)
def test_invalid_root_rejected(defect: str, message: str) -> None:
    graph = SRGBuilder()
    predicate = graph.add_predicate("Not a root")
    payload = graph.model_dump(mode="json")
    if defect == "missing":
        payload["nodes"].clear()
    elif defect == "wrong_id":
        payload["nodes"]["Root"]["id"] = "SN1"
    else:
        payload["nodes"]["Root"]["item_id"] = predicate

    assert_rejected(payload, message)


def test_validation_error_remains_catchable_as_value_error() -> None:
    graph = SRGBuilder()
    graph.nodes.clear()

    with pytest.raises(ValueError) as error:
        validate_srg(graph)

    assert type(error.value) is SRGValidationError


@pytest.mark.parametrize("reference", ["aggregator", "node", "source", "target"])
def test_dangling_reference_rejected_on_load(reference: str) -> None:
    graph = SRGBuilder()
    predicate = graph.add_predicate("Condition")
    aggregator = graph.add_aggregator(AllStrategy(), True, [predicate])
    node = graph.add_node(aggregator)
    graph.add_edge("Root", node)
    payload = graph.model_dump(mode="json")
    edge_id, edge = next(iter(payload["edges"].items()))
    if reference == "aggregator":
        payload["aggregators"][aggregator]["argument_ids"] = ["missing"]
        message = f"Aggregator {aggregator!r} refers to unknown symbol 'missing'"
    elif reference == "node":
        payload["nodes"][node]["item_id"] = "missing"
        message = f"Node {node!r} refers to unknown symbol 'missing'"
    elif reference == "source":
        edge["source"] = "SN999"
        message = f"Edge {edge_id!r} source refers to unknown graph node 'SN999'"
    else:
        edge["target"] = "SN999"
        message = f"Edge {edge_id!r} target refers to unknown graph node 'SN999'"

    assert_rejected(payload, message)


@pytest.mark.parametrize("store", ["predicates", "aggregators", "outcomes"])
def test_citation_id_naming_no_citation_rejected_after_json_loading(
    graph_with_symbols: SRG, store: str
) -> None:
    payload = graph_with_symbols.model_dump()
    symbol_id, symbol = next(iter(payload[store].items()))
    symbol["citation_ids"] = ["missing"]

    with pytest.raises(SRGValidationError) as error:
        load_srg(payload)

    assert str(error.value) == (
        f"{symbol_id!r} cites 'missing', which is not a citation in the graph"
    )


def test_second_node_wrapping_root_rejected_on_load(graph_with_symbols: SRG) -> None:
    payload = graph_with_symbols.model_dump()
    payload["nodes"]["SN_9"] = {"id": "SN_9", "item_id": "Root"}

    assert_rejected(payload, "Only the 'Root' node can wrap Root; 'SN_9' does too")


@pytest.mark.parametrize("argument", ["O1", "Root"])
def test_aggregator_over_an_outcome_or_root_rejected_on_load(
    graph_with_symbols: SRG, argument: str
) -> None:
    payload = graph_with_symbols.model_dump()
    payload["aggregators"]["A1"]["argument_ids"] = ["P1", argument]

    assert_rejected(
        payload,
        f"Aggregator 'A1' takes {argument!r} as an argument, but only "
        "predicates and aggregators can be decided",
    )


@pytest.mark.parametrize("cycle_length", [1, 2, 3])
def test_aggregator_cycles_rejected_even_when_disconnected(cycle_length: int) -> None:
    graph = SRGBuilder()
    previous = graph.add_predicate("Condition")
    aggregators = []
    for _ in range(cycle_length):
        previous = graph.add_aggregator(AllStrategy(), True, [previous])
        aggregators.append(previous)
    payload = graph.model_dump(mode="json")
    payload["aggregators"][aggregators[0]]["argument_ids"] = [aggregators[-1]]

    with pytest.raises(ValidationError, match="Aggregator dependency cycle: "):
        SRG.model_validate(payload)
    with pytest.raises(
        SRGValidationError, match="^Aggregator dependency cycle: "
    ) as error:
        validate_srg(SRGBuilder.model_validate(payload))
    assert isinstance(error.value.__cause__, CycleError)
    cycle = str(error.value).removeprefix("Aggregator dependency cycle: ").split(" → ")
    assert cycle[0] == cycle[-1]
    assert len(cycle) == cycle_length + 1
    for source, target in pairwise(cycle):
        assert target in payload["aggregators"][source]["argument_ids"]


@pytest.mark.parametrize("connected", [False, True])
@pytest.mark.parametrize("cycle_length", [1, 2, 3])
def test_graph_cycles_rejected(connected: bool, cycle_length: int) -> None:
    graph = SRGBuilder()
    nodes = [
        graph.add_node(graph.add_predicate(f"Condition {index}"))
        for index in range(cycle_length)
    ]
    if connected:
        graph.add_edge("Root", nodes[0])
    for source, target in zip(nodes, [*nodes[1:], nodes[0]], strict=True):
        graph.add_edge(source, target)

    with pytest.raises(SRGValidationError, match="^Graph edge cycle: ") as error:
        validate_srg(graph)
    assert isinstance(error.value.__cause__, CycleError)
    cycle = str(error.value).removeprefix("Graph edge cycle: ").split(" → ")
    assert cycle[0] == cycle[-1]
    assert len(cycle) == cycle_length + 1
    edges = {(edge.source, edge.target) for edge in graph.edges.values()}
    assert all(pair in edges for pair in pairwise(cycle))
