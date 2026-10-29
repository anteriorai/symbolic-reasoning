"""Structural checks for a completed SRG, independent of its transport or solver."""

import re
from graphlib import CycleError, TopologicalSorter

from symbolic_reasoning.gen.py.srg import SRG, Aggregator, Node

ROOT_ID = "Root"
_GRAPH_ID_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for model in (Aggregator, Node)
    for metadata in model.model_fields["id"].metadata
    if (pattern := getattr(metadata, "pattern", None))
)


def is_graph_id(symbol_id: str) -> bool:
    """Whether the ID takes the schema's aggregator or node ID format, Root included."""
    return any(pattern.fullmatch(symbol_id) for pattern in _GRAPH_ID_PATTERNS)


class SRGValidationError(ValueError):
    """The SRG has an invalid graph structure."""


def validate_srg(srg: SRG) -> None:
    """Raise ``SRGValidationError`` for invalid roots, symbols, references, or cycles.

    Check both aggregator dependencies and graph edges, including disconnected
    components. Nodes must reference a predicate, aggregator, outcome, or Root,
    and only the Root node may reference Root; aggregator arguments must
    reference a predicate or aggregator, since an outcome or Root is never
    decided. Edge endpoints must reference graph nodes.
    Each predicate, aggregator, outcome, and node is stored under its own ID.
    Predicate, aggregator, and outcome keys must be unique across those stores
    and must not use the reserved Root ID; predicate and outcome keys must not
    take the format of an aggregator or node ID.

    This check complements Pydantic's field validation. Every ``SRG`` runs it on
    construction; call it directly to check an ``SRGBuilder`` draft before
    building. It does not mutate the graph or require every symbol to be
    reachable or have an outcome.
    """
    _validate_root(srg)
    _validate_keys(srg)
    symbols = _validate_symbol_ids(srg)
    _validate_aggregators(srg, symbols)
    _validate_nodes(srg, symbols)
    _validate_citations(srg)
    _validate_edges(srg)


def _validate_root(srg: SRG) -> None:
    root = srg.nodes.get(ROOT_ID)
    if root is None:
        raise SRGValidationError("Graph is missing its Root node")
    if root.id != ROOT_ID:
        raise SRGValidationError(f"Root node must have id 'Root'; got {root.id!r}")
    if root.item_id != ROOT_ID:
        raise SRGValidationError(
            f"Root node must have item_id 'Root'; got {root.item_id!r}"
        )


def _validate_keys(srg: SRG) -> None:
    for name, store in (
        ("predicates", srg.predicates),
        ("aggregators", srg.aggregators),
        ("outcomes", srg.outcomes),
        ("nodes", srg.nodes),
    ):
        for key, item in store.items():
            if key != item.id:
                raise SRGValidationError(
                    f"Key {key!r} in {name} does not match the ID {item.id!r} it holds"
                )


def _validate_symbol_ids(srg: SRG) -> set[str]:
    owners = {ROOT_ID: "reserved Root symbol"}
    for name, store in (
        ("predicates", srg.predicates),
        ("aggregators", srg.aggregators),
        ("outcomes", srg.outcomes),
    ):
        for symbol_id in store:
            if symbol_id in owners:
                raise SRGValidationError(
                    f"Symbol ID {symbol_id!r} appears in both "
                    f"{owners[symbol_id]} and {name}"
                )
            if name != "aggregators" and is_graph_id(symbol_id):
                raise SRGValidationError(
                    f"Symbol ID {symbol_id!r} in {name} is reserved for graph IDs"
                )
            owners[symbol_id] = name

    return set(owners)


def _validate_aggregators(srg: SRG, symbols: set[str]) -> None:
    dependencies = {}
    for aggregator_id, aggregator in srg.aggregators.items():
        for argument_id in aggregator.argument_ids:
            if argument_id not in symbols:
                raise SRGValidationError(
                    f"Aggregator {aggregator_id!r} refers to unknown symbol {argument_id!r}"
                )
            if argument_id == ROOT_ID or argument_id in srg.outcomes:
                raise SRGValidationError(
                    f"Aggregator {aggregator_id!r} takes {argument_id!r} as an "
                    "argument, but only predicates and aggregators can be decided"
                )
        dependencies[aggregator_id] = aggregator.argument_ids
    try:
        tuple(TopologicalSorter(dependencies).static_order())
    except CycleError as exc:
        # TopologicalSorter reports dependency -> dependent; show the direction
        # of aggregator references instead: aggregator -> argument.
        cycle = " → ".join(reversed(exc.args[1]))
        raise SRGValidationError(f"Aggregator dependency cycle: {cycle}") from exc


def _validate_nodes(srg: SRG, symbols: set[str]) -> None:
    for node_id, node in srg.nodes.items():
        if node.item_id == ROOT_ID and node_id != ROOT_ID:
            raise SRGValidationError(
                f"Only the 'Root' node can wrap Root; {node_id!r} does too"
            )
        if node.item_id not in symbols:
            raise SRGValidationError(
                f"Node {node_id!r} refers to unknown symbol {node.item_id!r}"
            )


def _validate_citations(srg: SRG) -> None:
    citations = srg.citations or {}
    for store in (srg.predicates, srg.aggregators, srg.outcomes):
        for symbol_id, symbol in store.items():
            for citation_id in symbol.citation_ids or []:
                if citation_id not in citations:
                    raise SRGValidationError(
                        f"{symbol_id!r} cites {citation_id!r}, "
                        "which is not a citation in the graph"
                    )


def _validate_edges(srg: SRG) -> None:
    parents: dict[str, list[str]] = {node_id: [] for node_id in srg.nodes}
    for edge_id, edge in srg.edges.items():
        for role, endpoint in (("source", edge.source), ("target", edge.target)):
            if endpoint not in parents:
                raise SRGValidationError(
                    f"Edge {edge_id!r} {role} refers to unknown graph node {endpoint!r}"
                )
        parents[edge.target].append(edge.source)
    try:
        tuple(TopologicalSorter(parents).static_order())
    except CycleError as exc:
        cycle = " → ".join(exc.args[1])
        raise SRGValidationError(f"Graph edge cycle: {cycle}") from exc
