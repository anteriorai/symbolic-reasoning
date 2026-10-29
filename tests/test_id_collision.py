from collections.abc import Callable

import pytest

from symbolic_reasoning import (
    SRGBuilder,
    SRGValidationError,
)
from symbolic_reasoning.gen.py.srg import AllStrategy
from symbolic_reasoning.models import Node


def test_srg_instances_have_independent_id_counters() -> None:
    """Verify that each SRG instance has its own ID counters."""
    # Create first SRG and add some entities
    srg1 = SRGBuilder()
    p1_id = srg1.add_predicate("Question 1")
    p2_id = srg1.add_predicate("Question 2")
    agg1_id = srg1.add_aggregator(AllStrategy(), True, [p1_id, p2_id])
    outcome1_id = srg1.add_outcome("Outcome 1")
    node1_id = srg1.add_node(outcome1_id)

    # Create second SRG independently
    srg2 = SRGBuilder()
    p3_id = srg2.add_predicate("Question 3")
    p4_id = srg2.add_predicate("Question 4")
    agg2_id = srg2.add_aggregator(AllStrategy(), True, [p3_id, p4_id])
    outcome2_id = srg2.add_outcome("Outcome 2")
    node2_id = srg2.add_node(outcome2_id)

    # Verify that IDs start fresh in second SRG (no collision)
    assert p3_id == "P1", f"Expected P1, got {p3_id}"
    assert p4_id == "P2", f"Expected P2, got {p4_id}"
    assert agg2_id == "A1", f"Expected A1, got {agg2_id}"
    assert outcome2_id == "O1", f"Expected O1, got {outcome2_id}"
    assert node2_id == "SN_1", f"Expected SN_1, got {node2_id}"

    # Verify first SRG's IDs are still correct
    assert p1_id == "P1"
    assert p2_id == "P2"
    assert agg1_id == "A1"
    assert outcome1_id == "O1"
    assert node1_id == "SN_1"

    assert srg1.predicates.keys() == srg2.predicates.keys()
    assert srg1.aggregators.keys() == srg2.aggregators.keys()
    assert srg1.outcomes.keys() == srg2.outcomes.keys()


def test_aggregator_signatures_not_shared_across_instances() -> None:
    """Verify that aggregator signature cache is not shared across instances."""
    # Create first SRG with an aggregator
    srg1 = SRGBuilder()
    p1_id = srg1.add_predicate("Question 1")
    p2_id = srg1.add_predicate("Question 2")
    agg1_id = srg1.add_aggregator(AllStrategy(), True, [p1_id, p2_id])

    # Create second SRG with identical aggregator parameters
    srg2 = SRGBuilder()
    p3_id = srg2.add_predicate("Question 1")  # Same question text
    p4_id = srg2.add_predicate("Question 2")  # Same question text
    agg2_id = srg2.add_aggregator(AllStrategy(), True, [p3_id, p4_id])

    # Both should have their own A1 aggregator (not deduplicated across instances)
    assert agg1_id == "A1"
    assert agg2_id == "A1"

    # Verify they're in different SRG instances
    assert agg1_id in srg1.aggregators
    assert agg2_id in srg2.aggregators
    assert len(srg1.aggregators) == 1
    assert len(srg2.aggregators) == 1


def test_srg_deserialization_creates_fresh_counters() -> None:
    """Verify that deserializing an SRG creates fresh ID counters."""
    # Create an SRG
    srg1 = SRGBuilder()
    _ = srg1.add_predicate("Question 1")
    _ = srg1.add_outcome("Outcome 1")

    # Serialize and deserialize
    serialized = srg1.model_dump()
    srg2 = SRGBuilder.model_validate(serialized)

    # Add new entities to deserialized SRG
    p2_id = srg2.add_predicate("Question 2")
    outcome2_id = srg2.add_outcome("Outcome 2")

    # New IDs should continue the sequence (P2, O2), not start fresh
    assert p2_id == "P2", f"Expected P2, got {p2_id}"
    assert outcome2_id == "O2", f"Expected O2, got {outcome2_id}"

    # Original SRG should have only the original entities
    assert len(srg1.predicates) == 1
    assert len(srg1.outcomes) == 1

    # Deserialized SRG should have both original and new entities
    assert len(srg2.predicates) == 2
    assert len(srg2.outcomes) == 2


def test_concurrent_srg_creation_no_collision() -> None:
    """Verify that creating multiple SRGs in sequence doesn't cause collisions."""
    srgs = []

    # Create 5 SRG instances, each adding entities
    for i in range(5):
        srg = SRGBuilder()
        p_id = srg.add_predicate(f"Question {i}")
        o_id = srg.add_outcome(f"Outcome {i}")
        srgs.append((srg, p_id, o_id))

    # All should have the same IDs (P1, O1) since they're independent
    for i, (srg, p_id, o_id) in enumerate(srgs):
        assert p_id == "P1", f"SRG {i}: Expected P1, got {p_id}"
        assert o_id == "O1", f"SRG {i}: Expected O1, got {o_id}"
        assert len(srg.predicates) == 1
        assert len(srg.outcomes) == 1


def test_a_node_stored_under_a_symbol_id_is_rejected_when_built() -> None:
    graph = SRGBuilder()
    graph.add_predicate("Is it on file?", id="referral")
    graph.add_predicate("Is income verified?", id="income")
    graph.nodes["referral"] = Node(id="SN_9", item_id="income")

    with pytest.raises(
        SRGValidationError,
        match="Key 'referral' in nodes does not match the ID 'SN_9' it holds",
    ):
        graph.build()


def test_generated_symbol_ids_skip_ids_taken_in_other_stores() -> None:
    graph = SRGBuilder()
    graph.add_outcome("Named like a predicate", id="P1")

    assert graph.add_predicate("First question") == "P2"


@pytest.mark.parametrize(
    ("existing", "register", "message"),
    [
        (
            lambda srg: srg.add_outcome("Yes", id="adult"),
            lambda srg: srg.add_predicate("Q?", id="adult"),
            "Predicate ID 'adult' is already used by an outcome",
        ),
        (
            lambda srg: srg.add_predicate("Q?", id="x"),
            lambda srg: srg.add_outcome("Yes", id="x"),
            "Outcome ID 'x' is already used by a predicate",
        ),
        (
            lambda srg: None,
            lambda srg: srg.add_predicate("Q?", id="Root"),
            "Predicate ID 'Root' is reserved for graph IDs",
        ),
    ],
)
def test_register_rejects_an_id_another_symbol_uses(
    existing: Callable[[SRGBuilder], object],
    register: Callable[[SRGBuilder], object],
    message: str,
) -> None:
    srg = SRGBuilder()
    existing(srg)

    with pytest.raises(ValueError, match=message):
        register(srg)


@pytest.mark.parametrize(
    ("register", "kind"),
    [
        (
            lambda srg, i: srg.add_predicate("Q?", id=i),
            "Predicate",
        ),
        (
            lambda srg, i: srg.add_outcome("O", id=i),
            "Outcome",
        ),
    ],
)
def test_register_rejects_graph_ids_for_every_kind(
    register: Callable[[SRGBuilder, str], object], kind: str
) -> None:
    srg = SRGBuilder()

    for graph_id in ("Root", "A1", "SN_2", "SN3"):
        with pytest.raises(
            ValueError, match=f"{kind} ID '{graph_id}' is reserved for graph IDs"
        ):
            register(srg, graph_id)


def test_register_still_reuses_an_equivalent_aggregator() -> None:
    srg = SRGBuilder()
    p = srg.add_predicate("Q?")
    first = srg.add_aggregator(AllStrategy(), True, [p])

    assert srg.add_aggregator(AllStrategy(), True, [p], id="A50") == first
