"""
Core SRG functionality tests.

This module consolidates essential SRG model and execution tests, focusing on:
1. SRG construction and basic operations
2. Symbol evaluation (predicates, aggregators, outcomes)
3. Path traversal and outcome determination
4. Complex execution scenarios

Tests avoid redundancy and focus on behavior rather than structure.
"""

import pytest

from symbolic_reasoning import (
    SRGBuilder,
    apply_answers,
    outcomes,
    reasoning_trace,
)
from symbolic_reasoning.models import (
    SRG,
    AllStrategy,
    Answer,
    AtLeastStrategy,
    AtMostStrategy,
    ExactlyStrategy,
    ExecutionNotResolvedError,
    ReasoningTrace,
    SRGExecution,
    evaluate_symbol,
)
from symbolic_reasoning.models.srg_execution import (
    _answered_predicates,
    _outcome_paths,
    _predicates_under,
)

from .utils import (
    create_predicate_answers,
    get_aggregator_by_name,
)

# Test markers
pytestmark = pytest.mark.unit


class TestSRGConstruction:
    """Test core SRG construction functionality."""

    def test_srg_creation_with_context(self) -> None:
        """Test SRG creation with policy context."""
        context = "Medical treatment policy"
        srg = SRGBuilder()
        srg.policy_context = context

        assert srg.policy_context == context
        assert len(srg.predicates) == 0
        assert len(srg.outcomes) == 0
        assert len(srg.aggregators) == 0
        assert len(srg.nodes) == 1  # Only Root node
        assert "Root" in srg.nodes
        assert srg.nodes["Root"].item_id == "Root"

    def test_predicate_management(self, simple_srg: SRG) -> None:
        """Test predicate addition and retrieval."""
        builder = SRGBuilder.from_srg(simple_srg)
        pred_id = builder.add_predicate("New condition", "Test context")
        srg = builder.build()

        assert pred_id in srg.predicates
        assert pred_id not in simple_srg.predicates
        predicate = srg.predicates[pred_id]
        assert predicate.question == "New condition"
        assert predicate.context == "Test context"

    def test_aggregator_deduplication(
        self,
        aggregator_strategies: dict[
            str, AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy
        ],
    ) -> None:
        """Indistinguishable aggregators are deduplicated."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        agg1_id = srg.add_aggregator(
            strategy=aggregator_strategies["all_2"],
            truth_value=True,
            argument_ids=[p1_id, p2_id],
            name="Requirements",
        )
        agg2_id = srg.add_aggregator(
            strategy=AllStrategy(),
            truth_value=True,
            argument_ids=[p1_id, p2_id],
            name="Requirements",
        )

        assert agg1_id == agg2_id
        assert len(srg.aggregators) == 1

    def test_aggregator_argument_order_is_significant(self) -> None:
        """Reordered arguments are not deduplicated: order sets ask and trace order."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        agg1_id = srg.add_aggregator(AllStrategy(), True, [p1_id, p2_id])
        agg2_id = srg.add_aggregator(AllStrategy(), True, [p2_id, p1_id])

        assert agg1_id != agg2_id
        assert srg.aggregators[agg1_id].argument_ids == [p1_id, p2_id]
        assert srg.aggregators[agg2_id].argument_ids == [p2_id, p1_id]

    def test_aggregator_name_is_significant(self) -> None:
        """Differently named aggregators are kept apart rather than overwritten."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        agg1_id = srg.add_aggregator(AllStrategy(), True, [p1_id, p2_id], name="First")
        agg2_id = srg.add_aggregator(AllStrategy(), True, [p1_id, p2_id], name="Second")

        assert agg1_id != agg2_id
        assert srg.aggregators[agg1_id].name == "First"
        assert srg.aggregators[agg2_id].name == "Second"

    def test_aggregator_metadata_is_significant(self) -> None:
        """Metadata survives deduplication."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        plain_id = srg.add_aggregator(AllStrategy(), True, [p1_id, p2_id])
        annotated_id = srg.add_aggregator(
            AllStrategy(), True, [p1_id, p2_id], metadata={"custom": "value"}
        )

        assert plain_id != annotated_id
        assert srg.aggregators[plain_id].metadata is None
        assert srg.aggregators[annotated_id].metadata == {"custom": "value"}

    def test_metadata_values_are_not_conflated_by_type(self) -> None:
        """``True`` and ``1`` stay distinct, though Python's ``==`` conflates them."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        bool_id = srg.add_aggregator(
            AllStrategy(), True, [p1_id, p2_id], metadata={"custom": True}
        )
        int_id = srg.add_aggregator(
            AllStrategy(), True, [p1_id, p2_id], metadata={"custom": 1}
        )

        assert bool_id != int_id

    def test_aggregator_dedup_follows_edits(self) -> None:
        """An edited aggregator no longer answers for what it used to check."""
        srg = SRGBuilder()
        adult = srg.add_predicate("Adult?")
        consent = srg.add_predicate("Consent?")
        first = srg.add_aggregator(AllStrategy(), True, [adult])
        srg.aggregators[first] = srg.aggregators[first].model_copy(
            update={"argument_ids": [consent]}
        )

        gate = srg.add_aggregator(AllStrategy(), True, [adult])

        assert gate != first
        assert srg.aggregators[gate].argument_ids == [adult]

    def test_aggregator_dedup_follows_removals(self) -> None:
        srg = SRGBuilder()
        question = srg.add_predicate("Q?")
        removed = srg.add_aggregator(AllStrategy(), True, [question])
        del srg.aggregators[removed]

        again = srg.add_aggregator(AllStrategy(), True, [question])

        assert again in srg.aggregators
        assert srg.aggregators[again].argument_ids == [question]

    def test_adding_an_edited_aggregator_again_returns_its_id(self) -> None:
        srg = SRGBuilder()
        adult = srg.add_predicate("Adult?")
        consent = srg.add_predicate("Consent?")
        first = srg.add_aggregator(AllStrategy(), True, [adult])
        srg.aggregators[first] = srg.aggregators[first].model_copy(
            update={"argument_ids": [consent]}
        )

        again = srg.add_aggregator(AllStrategy(), True, [consent], id=first)

        assert again == first
        assert list(srg.aggregators) == [first]

    def test_aggregator_signature_cache_survives_round_trip(self) -> None:
        """A deserialised SRG rebuilds signatures without collapsing aggregators."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")
        srg.add_aggregator(AllStrategy(), True, [p1_id, p2_id], name="First")
        srg.add_aggregator(AllStrategy(), True, [p1_id, p2_id], name="Second")

        reloaded = SRGBuilder.model_validate(srg.model_dump(mode="json"))

        assert len(reloaded.aggregators) == 2
        # Dedup still works against the rebuilt cache.
        assert reloaded.add_aggregator(
            AllStrategy(), True, [p1_id, p2_id], name="First"
        ) in set(reloaded.aggregators)
        assert len(reloaded.aggregators) == 2

    def test_edge_management(self) -> None:
        """Test edge creation."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Condition 1")
        p2_id = srg.add_predicate("Condition 2")
        outcome_id = srg.add_outcome("Result")

        p1_node = srg.add_node(p1_id)
        p2_node = srg.add_node(p2_id)
        outcome_node = srg.add_node(outcome_id)

        # Explicitly connect root to p1
        srg.add_edge("Root", p1_node, condition=True)
        root_to_p1_key = f"E_Root->{p1_node}"
        assert root_to_p1_key in srg.edges

        # Add edges between predicates and outcome
        srg.add_edge(p1_node, p2_node, condition=True)
        srg.add_edge(p2_node, outcome_node, condition=True)

        # Root connection should still exist (explicit management)
        assert root_to_p1_key in srg.edges

        # Verify Root node exists
        assert "Root" in srg.nodes
        assert srg.nodes["Root"].item_id == "Root"

    def test_add_node_requires_registered_symbol(self) -> None:
        """Nodes should only be created for registered predicates, aggregators, or outcomes."""
        srg = SRGBuilder()

        with pytest.raises(ValueError, match="unknown item ID 'missing_symbol'"):
            srg.add_node("missing_symbol")

    @pytest.mark.parametrize("argument", ["outcome", "Root"])
    def test_add_aggregator_rejects_undecidable_arguments(self, argument: str) -> None:
        """An outcome or Root is never decided, so no aggregator can use it."""
        srg = SRGBuilder()
        predicate = srg.add_predicate("Eligible?")
        undecidable = srg.add_outcome("Approved") if argument == "outcome" else "Root"

        with pytest.raises(ValueError, match=f"{undecidable!r} as an argument"):
            srg.add_aggregator(AllStrategy(), True, [predicate, undecidable])

        assert srg.aggregators == {}

    def test_add_outcome_rejects_an_id_an_aggregator_already_takes(self) -> None:
        """Registering the outcome after the aggregator is caught too."""
        srg = SRGBuilder()
        aggregator = srg.add_aggregator(AllStrategy(), True, ["O1"])

        with pytest.raises(ValueError, match=f"{aggregator!r} takes 'O1'"):
            srg.add_outcome("Approved")

        assert srg.outcomes == {}

    def test_add_node_rejects_a_second_root(self) -> None:
        """Only the graph's Root node wraps Root; a second one is never entered."""
        srg = SRGBuilder()

        with pytest.raises(ValueError, match="Only the 'Root' node can wrap Root"):
            srg.add_node("Root")

        assert list(srg.nodes) == ["Root"]

    def test_add_edge_requires_existing_nodes(self) -> None:
        """Edge endpoints must be existing graph nodes."""
        srg = SRGBuilder()
        predicate_id = srg.add_predicate("Condition 1")
        predicate_node = srg.add_node(predicate_id)

        with pytest.raises(ValueError, match="unknown source node 'SN_999'"):
            srg.add_edge("SN_999", predicate_node, condition=True)

        with pytest.raises(ValueError, match="unknown target node 'SN_999'"):
            srg.add_edge(predicate_node, "SN_999", condition=True)

    @pytest.mark.parametrize("first_condition", [True, False])
    def test_add_edge_allows_opposite_conditions_but_rejects_duplicates(
        self, first_condition: bool
    ) -> None:
        srg = SRGBuilder()
        predicate_id = srg.add_predicate("Condition 1")
        outcome_id = srg.add_outcome("Result")
        predicate_node = srg.add_node(predicate_id)
        outcome_node = srg.add_node(outcome_id)

        srg.add_edge("Root", predicate_node)
        for condition in (first_condition, not first_condition):
            srg.add_edge(predicate_node, outcome_node, condition=condition)
            before = srg.model_dump()
            with pytest.raises(ValueError, match="duplicate edge"):
                srg.add_edge(predicate_node, outcome_node, condition=condition)
            assert srg.model_dump() == before

        assert len(srg.edges) == 3
        for condition in (True, False):
            execution = SRGExecution(
                srg=srg.build(),
                answers={predicate_id: Answer(is_met=condition, reasoning="Test")},
            )
            assert [outcome.id for outcome in outcomes(execution)] == [outcome_id]

    @pytest.mark.parametrize("legacy_id", [True, False])
    def test_add_edge_preserves_deserialized_edge_ids(self, legacy_id: bool) -> None:
        srg = SRGBuilder()
        source = srg.add_node(srg.add_predicate("Condition"))
        target = srg.add_node(srg.add_outcome("Result"))
        srg.add_edge(source, target, condition=False)
        data = srg.model_dump()
        stored_id = f"E_{source}->{target}" if legacy_id else "custom-edge"
        data["edges"] = {stored_id: next(iter(data["edges"].values()))}
        srg = SRGBuilder.model_validate(data)
        original = srg.edges[stored_id].model_copy(deep=True)

        with pytest.raises(ValueError, match="duplicate edge"):
            srg.add_edge(source, target, condition=False)
        srg.add_edge(source, target, condition=True)
        with pytest.raises(ValueError, match="duplicate edge"):
            srg.add_edge(source, target, condition=True)

        assert srg.edges[stored_id] == original
        assert len(srg.edges) == 2
        assert {edge.condition for edge in srg.edges.values()} == {True, False}

    def test_add_edge_avoids_ids_used_by_unrelated_edges(self) -> None:
        srg = SRGBuilder()
        source = srg.add_node(srg.add_predicate("Condition"))
        target = srg.add_node(srg.add_outcome("Result"))
        srg.add_edge("Root", source)
        original = next(iter(srg.edges.values()))
        preferred_key = f"E_{source}->{target}"
        srg.edges = {preferred_key: original}

        srg.add_edge(source, target)

        assert srg.edges[preferred_key] == original
        assert len(srg.edges) == 2
        built = srg.build()
        assert [
            (edge.target, edge.condition)
            for edge in built.edges.values()
            if edge.source == source
        ] == [(target, True)]


class TestSymbolEvaluation:
    """Test symbol evaluation for different entity types."""

    def test_predicate_evaluation(
        self, simple_srg: SRG, standard_answers: dict[str, Answer]
    ) -> None:
        """Test predicate symbol evaluation."""
        execution = SRGExecution(srg=simple_srg)
        pred_ids = list(simple_srg.predicates.keys())

        # No answer - should return None
        assert evaluate_symbol(execution, pred_ids[0]) is None

        # With answer - should return answer value
        execution = apply_answers(
            execution, {pred_ids[0]: standard_answers["all_true"]}
        )
        assert evaluate_symbol(execution, pred_ids[0]) is True

        execution = apply_answers(
            execution, {pred_ids[0]: standard_answers["all_false"]}
        )
        assert evaluate_symbol(execution, pred_ids[0]) is False

    def test_root_evaluation(self) -> None:
        """Test root symbol evaluation."""
        srg = SRGBuilder()
        execution = SRGExecution(srg=srg.build())
        assert evaluate_symbol(execution, "Root") is True

    def test_outcome_evaluation(self) -> None:
        """Test outcome symbol evaluation."""
        srg = SRGBuilder()
        outcome_id = srg.add_outcome("Test outcome")
        execution = SRGExecution(srg=srg.build())
        assert evaluate_symbol(execution, outcome_id) is None

    def test_node_evaluation(
        self, simple_srg: SRG, standard_answers: dict[str, Answer]
    ) -> None:
        """Test node symbol evaluation delegates to item_id."""
        pred_ids = list(simple_srg.predicates.keys())
        builder = SRGBuilder.from_srg(simple_srg)
        node_id = builder.add_node(pred_ids[0])

        execution = SRGExecution(
            srg=builder.build(), answers={pred_ids[0]: standard_answers["all_true"]}
        )

        assert evaluate_symbol(execution, node_id) is True


class TestAggregatorEvaluation:
    """Test aggregator evaluation with different strategies."""

    @pytest.mark.parametrize(
        "strategy_key,answer_values,expected",
        [
            ("all_2", [True, True], True),  # All strategy success
            ("all_2", [True, False], False),  # All strategy failure
            ("atleast_2", [True, True, False], True),  # AtLeast success
            ("atleast_2", [True, False, False], False),  # AtLeast failure
            ("atmost_1", [True, False], True),  # AtMost success
            ("atmost_1", [True, True], False),  # AtMost failure
            ("exactly_2", [True, True, False], True),  # Exactly success
            ("exactly_2", [True, False, False], False),  # Exactly failure
        ],
    )
    def test_aggregator_strategies(
        self,
        aggregator_strategies: dict[
            str, AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy
        ],
        strategy_key: str,
        answer_values: list[bool],
        expected: bool,
    ) -> None:
        """Test aggregator evaluation with different strategies and answer combinations."""
        srg = SRGBuilder()
        pred_ids = [
            srg.add_predicate(f"Question {i + 1}") for i in range(len(answer_values))
        ]

        agg_id = srg.add_aggregator(
            strategy=aggregator_strategies[strategy_key],
            truth_value=True,
            argument_ids=pred_ids,
        )

        execution = SRGExecution(srg=srg.build())
        for pred_id, answer_value in zip(pred_ids, answer_values, strict=False):
            execution = apply_answers(
                execution,
                {
                    pred_id: Answer(
                        is_met=answer_value, reasoning=f"Answer {answer_value}"
                    )
                },
            )

        assert evaluate_symbol(execution, agg_id) is expected

    def test_negative_truth_value(
        self,
        aggregator_strategies: dict[
            str, AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy
        ],
    ) -> None:
        """Test aggregator with negative truth value (looking for false)."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        agg_id = srg.add_aggregator(
            strategy=aggregator_strategies["all_2"],
            truth_value=False,  # Looking for all false
            argument_ids=[p1_id, p2_id],
        )

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {p1_id: Answer(is_met=False, reasoning="P1 false")}
        )
        execution = apply_answers(
            execution, {p2_id: Answer(is_met=False, reasoning="P2 false")}
        )

        assert (
            evaluate_symbol(execution, agg_id) is True
        )  # All are false, matches truth_value=False

    def test_missing_answers(
        self,
        aggregator_strategies: dict[
            str, AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy
        ],
    ) -> None:
        """Test aggregator evaluation with missing answers."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")

        agg_id = srg.add_aggregator(
            strategy=aggregator_strategies["all_2"],
            truth_value=True,
            argument_ids=[p1_id, p2_id],
        )

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {p1_id: Answer(is_met=True, reasoning="P1 true")}
        )
        # p2_id has no answer

        assert evaluate_symbol(execution, agg_id) is None

    def test_nested_aggregators(
        self,
        aggregator_strategies: dict[
            str, AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy
        ],
    ) -> None:
        """Test evaluation of nested aggregators."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Question 1")
        p2_id = srg.add_predicate("Question 2")
        p3_id = srg.add_predicate("Question 3")

        # Inner aggregator: All(P1, P2)
        inner_agg_id = srg.add_aggregator(
            strategy=aggregator_strategies["all_2"],
            truth_value=True,
            argument_ids=[p1_id, p2_id],
        )

        # Outer aggregator: AtLeast(1, inner_agg, P3)
        outer_agg_id = srg.add_aggregator(
            strategy=aggregator_strategies["atleast_1"],
            truth_value=True,
            argument_ids=[inner_agg_id, p3_id],
        )

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {p1_id: Answer(is_met=True, reasoning="P1 true")}
        )
        execution = apply_answers(
            execution, {p2_id: Answer(is_met=True, reasoning="P2 true")}
        )
        execution = apply_answers(
            execution, {p3_id: Answer(is_met=False, reasoning="P3 false")}
        )

        assert evaluate_symbol(execution, inner_agg_id) is True
        assert evaluate_symbol(execution, outer_agg_id) is True


class TestPathTraversal:
    """Test path traversal and outcome determination."""

    def test_simple_path_traversal(self, branching_srg: SRG) -> None:
        """Test getting outcome paths in simple branching case."""
        execution = SRGExecution(srg=branching_srg)
        pred_ids = list(branching_srg.predicates.keys())

        # Test true path
        execution = apply_answers(
            execution, {pred_ids[0]: Answer(is_met=True, reasoning="Condition met")}
        )
        outcome_paths = _outcome_paths(execution)

        assert len(outcome_paths) == 1
        outcome, predicate_answer_pairs = outcome_paths[0]
        assert outcome.description == "Approved"
        assert len(predicate_answer_pairs) == 1

    def test_multiple_outcome_paths(self, branching_srg: SRG) -> None:
        """Test execution with different conditions leading to different outcomes."""
        pred_ids = list(branching_srg.predicates.keys())

        # Test false path
        execution = SRGExecution(srg=branching_srg)
        execution = apply_answers(
            execution,
            {pred_ids[0]: Answer(is_met=False, reasoning="Condition not met")},
        )

        outcome_paths = _outcome_paths(execution)
        assert len(outcome_paths) == 1
        assert outcome_paths[0][0].description == "Denied"

    def test_aggregator_path_traversal(
        self, medical_approval_srg: SRG, standard_answers: dict[str, Answer]
    ) -> None:
        """Test path traversal through aggregator chains."""
        execution = SRGExecution(srg=medical_approval_srg)

        # Set up approval scenario
        answers = create_predicate_answers(medical_approval_srg, "all_true")
        # Override emergency to false so we take normal path
        emergency_pred = next(
            pred_id
            for pred_id, pred in medical_approval_srg.predicates.items()
            if "emergency" in pred.question.lower()
        )
        answers[emergency_pred] = standard_answers["not_emergency"]

        execution = apply_answers(execution, answers)

        outcome_paths = _outcome_paths(execution)
        assert len(outcome_paths) >= 1

        # Should reach approval outcome
        outcomes = [path[0].description for path in outcome_paths]
        assert "Treatment Approved" in outcomes

    def test_missing_answer_error(self, simple_srg: SRG) -> None:
        """Interpreting an execution that still needs answers is an error."""
        execution = SRGExecution(srg=simple_srg)
        pred_ids = list(simple_srg.predicates.keys())

        # Only provide answer for first predicate
        execution = apply_answers(
            execution, {pred_ids[0]: Answer(is_met=True, reasoning="First answer")}
        )
        # Second predicate has no answer

        with pytest.raises(ExecutionNotResolvedError, match="not resolved"):
            _outcome_paths(execution)


class TestPredicateWalk:
    """Collecting an item's predicates walks the item DAG, not a tree."""

    def test_shared_sub_policy_is_walked_once(self) -> None:
        """Two parents expressing one sub-policy share its id, and it is entered once."""
        srg = SRGBuilder()
        left_id, right_id = (srg.add_predicate(f"Shared {i}") for i in range(2))
        shared_agg_id = srg.add_aggregator(AllStrategy(), True, [left_id, right_id])
        only_a_id = srg.add_predicate("Only A")
        only_b_id = srg.add_predicate("Only B")
        parent_a = srg.add_aggregator(AllStrategy(), True, [shared_agg_id, only_a_id])
        parent_b = srg.add_aggregator(AllStrategy(), True, [shared_agg_id, only_b_id])
        root_agg_id = srg.add_aggregator(AllStrategy(), True, [parent_a, parent_b])

        assert parent_a != parent_b
        assert [p.id for p in _predicates_under(srg.build(), root_agg_id)] == [
            left_id,
            right_id,
            only_a_id,
            only_b_id,
        ]

    def test_sharing_does_not_multiply_the_walk(self) -> None:
        """Eighteen levels is 19 items but 2**18 root-to-leaf paths."""
        srg = SRGBuilder()
        leaf_id = srg.add_predicate("Leaf")
        top_id = leaf_id
        for _ in range(18):
            top_id = srg.add_aggregator(AllStrategy(), True, [top_id, top_id])

        assert len(srg.aggregators) == 18
        assert [p.id for p in _predicates_under(srg.build(), top_id)] == [leaf_id]


class TestAnsweredPredicates:
    """``answered_predicates`` reports what was answered, not what mattered."""

    @staticmethod
    def _execution(
        strategy: AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy,
        answers: list[bool | None],
        truth_value: bool = True,
    ) -> tuple[SRGExecution, str, list[str]]:
        srg = SRGBuilder()
        pred_ids = [srg.add_predicate(f"Question {i}") for i in range(len(answers))]
        agg_id = srg.add_aggregator(strategy, truth_value, pred_ids)

        execution = SRGExecution(srg=srg.build())
        for pred_id, is_met in zip(pred_ids, answers, strict=True):
            if is_met is not None:
                execution = apply_answers(
                    execution, {pred_id: Answer(is_met=is_met, reasoning="r")}
                )
        return execution, agg_id, pred_ids

    def test_answered_predicate_entity(self) -> None:
        srg = SRGBuilder()
        pred_id = srg.add_predicate("Test question")
        execution = SRGExecution(srg=srg.build())

        assert _answered_predicates(execution, pred_id) == []

        execution = apply_answers(
            execution, {pred_id: Answer(is_met=True, reasoning="Test")}
        )
        assert [p.id for p in _answered_predicates(execution, pred_id)] == [pred_id]

    def test_reports_every_answer_regardless_of_verdict(self) -> None:
        """A satisfied and a failed AllStrategy both report all three answers."""
        met, agg_id, pred_ids = self._execution(AllStrategy(), [True, True, True])
        assert [p.id for p in _answered_predicates(met, agg_id)] == pred_ids

        # Previously the walk stopped at the first failure, hiding P3.
        unmet, agg_id, pred_ids = self._execution(AllStrategy(), [True, False, True])
        assert evaluate_symbol(unmet, agg_id) is False
        assert [p.id for p in _answered_predicates(unmet, agg_id)] == pred_ids

    def test_never_reports_an_unanswered_predicate(self) -> None:
        """An unanswered argument is absent, even when it precedes the cause."""
        execution, agg_id, pred_ids = self._execution(
            AllStrategy(), [True, None, False]
        )

        assert evaluate_symbol(execution, agg_id) is False
        assert [p.id for p in _answered_predicates(execution, agg_id)] == [
            pred_ids[0],
            pred_ids[2],
        ]

    def test_counted_strategies_report_uncounted_answers(self) -> None:
        """Exactly(2) reports the answered False that did not count toward it."""
        execution, agg_id, pred_ids = self._execution(
            ExactlyStrategy(count=2), [True, True, False]
        )

        assert evaluate_symbol(execution, agg_id) is True
        assert [p.id for p in _answered_predicates(execution, agg_id)] == pred_ids

    def test_negated_aggregator_reports_the_same_answers(self) -> None:
        """truth_value flips the verdict, not which answers are reported."""
        execution, agg_id, pred_ids = self._execution(
            AllStrategy(), [False, False, False], truth_value=False
        )

        assert evaluate_symbol(execution, agg_id) is True
        assert [p.id for p in _answered_predicates(execution, agg_id)] == pred_ids

    def test_shared_predicate_reported_once(self) -> None:
        """A predicate reachable through two argument subtrees appears once."""
        srg = SRGBuilder()
        shared_id = srg.add_predicate("Shared")
        other_id = srg.add_predicate("Other")
        left_id = srg.add_aggregator(AllStrategy(), True, [shared_id, other_id])
        right_id = srg.add_aggregator(AtLeastStrategy(count=1), True, [shared_id])
        root_agg_id = srg.add_aggregator(AllStrategy(), True, [left_id, right_id])

        execution = SRGExecution(srg=srg.build())
        for pred_id in (shared_id, other_id):
            execution = apply_answers(
                execution, {pred_id: Answer(is_met=True, reasoning="r")}
            )

        assert [p.id for p in _answered_predicates(execution, root_agg_id)] == [
            shared_id,
            other_id,
        ]

    def test_root_and_outcome_have_no_predicates(self) -> None:
        srg = SRGBuilder()
        outcome_id = srg.add_outcome("Denied")
        execution = SRGExecution(srg=srg.build())

        assert _answered_predicates(execution, "Root") == []
        assert _answered_predicates(execution, outcome_id) == []

    def test_node_reports_the_item_it_wraps(self) -> None:
        """A node id is accepted and answers for the wrapped item."""
        srg = SRGBuilder()
        pred_ids = [srg.add_predicate(f"Question {i}") for i in range(2)]
        agg_id = srg.add_aggregator(AllStrategy(), True, pred_ids)
        node_id = srg.add_node(agg_id)

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {pred_ids[0]: Answer(is_met=True, reasoning="r")}
        )

        assert [p.id for p in _answered_predicates(execution, node_id)] == [pred_ids[0]]


class TestComplexScenarios:
    """Test complex execution scenarios."""

    def test_medical_approval_workflow(
        self, medical_approval_srg: SRG, standard_answers: dict[str, Answer]
    ) -> None:
        """Test complex medical approval workflow."""
        # Test approval case
        execution_approve = SRGExecution(srg=medical_approval_srg)

        # Find predicate IDs by question content
        pred_mapping = {}
        for pred_id, pred in medical_approval_srg.predicates.items():
            if "age" in pred.question.lower():
                pred_mapping["age"] = pred_id
            elif "insurance" in pred.question.lower():
                pred_mapping["insurance"] = pred_id
            elif "diagnosis" in pred.question.lower():
                pred_mapping["diagnosis"] = pred_id
            elif "severe" in pred.question.lower():
                pred_mapping["severity"] = pred_id
            elif "cost" in pred.question.lower():
                pred_mapping["cost"] = pred_id
            elif "emergency" in pred.question.lower():
                pred_mapping["emergency"] = pred_id

        # Set up approval scenario
        execution_approve = apply_answers(
            execution_approve, {pred_mapping["age"]: standard_answers["age_valid"]}
        )
        execution_approve = apply_answers(
            execution_approve,
            {pred_mapping["insurance"]: standard_answers["insurance_valid"]},
        )
        execution_approve = apply_answers(
            execution_approve,
            {pred_mapping["diagnosis"]: standard_answers["diagnosis_confirmed"]},
        )
        execution_approve = apply_answers(
            execution_approve,
            {pred_mapping["severity"]: standard_answers["condition_severe"]},
        )
        execution_approve = apply_answers(
            execution_approve,
            {pred_mapping["cost"]: standard_answers["cost_acceptable"]},
        )
        execution_approve = apply_answers(
            execution_approve,
            {pred_mapping["emergency"]: standard_answers["not_emergency"]},
        )

        # Verify aggregators evaluate correctly
        basic_agg_id = get_aggregator_by_name(medical_approval_srg, "Basic Eligibility")
        medical_agg_id = get_aggregator_by_name(
            medical_approval_srg, "Medical Requirements"
        )
        final_agg_id = get_aggregator_by_name(medical_approval_srg, "Final Decision")

        assert evaluate_symbol(execution_approve, basic_agg_id) is True
        assert evaluate_symbol(execution_approve, medical_agg_id) is True
        assert evaluate_symbol(execution_approve, final_agg_id) is True

        # Test denial case (insurance fails)
        execution_deny = SRGExecution(srg=medical_approval_srg)
        execution_deny = apply_answers(
            execution_deny, {pred_mapping["age"]: standard_answers["age_valid"]}
        )
        execution_deny = apply_answers(
            execution_deny,
            {pred_mapping["insurance"]: standard_answers["insurance_invalid"]},
        )
        execution_deny = apply_answers(
            execution_deny,
            {pred_mapping["diagnosis"]: standard_answers["diagnosis_confirmed"]},
        )
        execution_deny = apply_answers(
            execution_deny,
            {pred_mapping["severity"]: standard_answers["condition_severe"]},
        )
        execution_deny = apply_answers(
            execution_deny, {pred_mapping["cost"]: standard_answers["cost_acceptable"]}
        )
        execution_deny = apply_answers(
            execution_deny,
            {pred_mapping["emergency"]: standard_answers["not_emergency"]},
        )

        assert evaluate_symbol(execution_deny, basic_agg_id) is False
        assert evaluate_symbol(execution_deny, final_agg_id) is False

    def test_unknown_symbol_type(self) -> None:
        """Test evaluating unknown symbol type raises error."""
        srg = SRGBuilder()
        execution = SRGExecution(srg=srg.build())

        with pytest.raises(TypeError, match="Unknown symbol type"):
            evaluate_symbol(execution, "UNKNOWN_TYPE")


class TestInterpretationAPI:
    """Test user-facing SRGExecution interpretation APIs."""

    def test_reasoning_trace_and_outcomes(self, branching_srg: SRG) -> None:
        """reasoning_trace() and outcomes() should return user-friendly results."""
        execution = SRGExecution(srg=branching_srg)
        pred_ids = list(branching_srg.predicates.keys())
        execution = apply_answers(
            execution, {pred_ids[0]: Answer(is_met=True, reasoning="Condition met")}
        )

        trace = reasoning_trace(execution)
        assert isinstance(trace, ReasoningTrace)
        assert len(trace.outcome_paths) == 1
        outcome_id = trace.outcome_paths[0].outcome_id
        assert branching_srg.outcomes[outcome_id].description == "Approved"
        assert len(trace.outcome_paths[0].steps) == 1
        assert trace.outcome_paths[0].steps[0].predicate_id == pred_ids[0]
        assert trace.outcome_paths[0].steps[0].is_met is True
        assert len(trace.all_paths) >= 1

        reached_outcomes = outcomes(execution)
        assert len(reached_outcomes) == 1
        assert reached_outcomes[0].description == "Approved"

    def test_explain_outcome_and_has_outcome(self, branching_srg: SRG) -> None:
        """Outcome-scoped helpers should filter and check by outcome ID."""
        execution = SRGExecution(srg=branching_srg)
        pred_ids = list(branching_srg.predicates.keys())
        execution = apply_answers(
            execution,
            {pred_ids[0]: Answer(is_met=False, reasoning="Condition not met")},
        )

        denied_outcome_id = next(
            outcome_id
            for outcome_id, outcome in branching_srg.outcomes.items()
            if outcome.description == "Denied"
        )
        approved_outcome_id = next(
            outcome_id
            for outcome_id, outcome in branching_srg.outcomes.items()
            if outcome.description == "Approved"
        )

        denied_traces = [
            p
            for p in reasoning_trace(execution).outcome_paths
            if p.outcome_id == denied_outcome_id
        ]
        assert len(denied_traces) == 1
        assert denied_traces[0].outcome_id == denied_outcome_id
        assert (denied_outcome_id in {o.id for o in outcomes(execution)}) is True
        assert (approved_outcome_id in {o.id for o in outcomes(execution)}) is False

    def test_all_paths_when_no_outcome(self) -> None:
        """all_paths should capture the explored path even when no outcome is reached."""
        srg = SRGBuilder()
        predicate_id = srg.add_predicate("Condition")
        outcome_id = srg.add_outcome("Approved")
        predicate_node = srg.add_node(predicate_id)
        outcome_node = srg.add_node(outcome_id)
        srg.add_edge("Root", predicate_node, condition=True)
        srg.add_edge(predicate_node, outcome_node, condition=True)

        # Predicate evaluates to False, so the only edge to the outcome is not traversed.
        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution,
            {predicate_id: Answer(is_met=False, reasoning="Condition failed")},
        )

        trace = reasoning_trace(execution)
        assert len(trace.outcome_paths) == 0
        assert len(trace.all_paths) == 1
        assert len(trace.all_paths[0].steps) == 1
        assert trace.all_paths[0].steps[0].predicate_id == predicate_id

    def test_reasoning_trace_mixed_execution(self) -> None:
        """reasoning_trace() should capture both outcome and non-outcome paths."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Path 1 condition")
        p2_id = srg.add_predicate("Path 2 condition")
        o1_id = srg.add_outcome("Outcome 1")
        o2_id = srg.add_outcome("Outcome 2")

        p1_node = srg.add_node(p1_id)
        p2_node = srg.add_node(p2_id)
        o1_node = srg.add_node(o1_id)
        o2_node = srg.add_node(o2_id)

        srg.add_edge("Root", p1_node, condition=True)
        srg.add_edge("Root", p2_node, condition=True)
        srg.add_edge(p1_node, o1_node, condition=True)
        srg.add_edge(p2_node, o2_node, condition=True)

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {p1_id: Answer(is_met=True, reasoning="Path 1 passes")}
        )
        execution = apply_answers(
            execution, {p2_id: Answer(is_met=False, reasoning="Path 2 fails")}
        )

        trace = reasoning_trace(execution)
        assert len(trace.outcome_paths) == 1
        assert trace.outcome_paths[0].outcome_id == o1_id
        # all_paths covers both the successful and dead-end paths
        assert len(trace.all_paths) == 2
        all_pred_ids = {
            step.predicate_id for trace in trace.all_paths for step in trace.steps
        }
        assert p1_id in all_pred_ids
        assert p2_id in all_pred_ids

    def test_explain_empty_when_no_outcome(self) -> None:
        """explain() should return an empty list when no outcome is reached."""
        srg = SRGBuilder()
        p_id = srg.add_predicate("Condition")
        o_id = srg.add_outcome("Result")
        p_node = srg.add_node(p_id)
        o_node = srg.add_node(o_id)
        srg.add_edge("Root", p_node, condition=True)
        srg.add_edge(p_node, o_node, condition=True)

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {p_id: Answer(is_met=False, reasoning="Fails")}
        )

        assert reasoning_trace(execution).outcome_paths == []

    def test_explain_outcome_empty_for_unreached_outcome(
        self, branching_srg: SRG
    ) -> None:
        """explain_outcome() should return empty list for an outcome not reached."""
        execution = SRGExecution(srg=branching_srg)
        pred_ids = list(branching_srg.predicates.keys())
        execution = apply_answers(
            execution, {pred_ids[0]: Answer(is_met=True, reasoning="Condition met")}
        )

        approved_id = next(
            oid
            for oid, o in branching_srg.outcomes.items()
            if o.description == "Approved"
        )
        denied_id = next(
            oid
            for oid, o in branching_srg.outcomes.items()
            if o.description == "Denied"
        )

        assert (
            len(
                [
                    p
                    for p in reasoning_trace(execution).outcome_paths
                    if p.outcome_id == approved_id
                ]
            )
            == 1
        )
        assert [
            p
            for p in reasoning_trace(execution).outcome_paths
            if p.outcome_id == denied_id
        ] == []

    def test_outcomes_deduplication(self) -> None:
        """outcomes() should return each outcome only once even if reached via multiple paths."""
        srg = SRGBuilder()
        p1_id = srg.add_predicate("Path A condition")
        p2_id = srg.add_predicate("Path B condition")
        o_id = srg.add_outcome("Shared Outcome")

        p1_node = srg.add_node(p1_id)
        p2_node = srg.add_node(p2_id)
        o1_node = srg.add_node(o_id)
        o2_node = srg.add_node(o_id)

        srg.add_edge("Root", p1_node, condition=True)
        srg.add_edge("Root", p2_node, condition=True)
        srg.add_edge(p1_node, o1_node, condition=True)
        srg.add_edge(p2_node, o2_node, condition=True)

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {p1_id: Answer(is_met=True, reasoning="A passes")}
        )
        execution = apply_answers(
            execution, {p2_id: Answer(is_met=True, reasoning="B passes")}
        )

        # explain() should have two traces (one per path)
        assert len(reasoning_trace(execution).outcome_paths) == 2
        # outcomes() should deduplicate to one
        assert len(outcomes(execution)) == 1
        assert outcomes(execution)[0].id == o_id


class TestEquality:
    """Test SRG equality and hashing for complex structures."""

    def test_complex_srg_equality(self) -> None:
        """Test that structurally identical complex SRGs are equal."""

        def create_complex_srg() -> SRG:
            srg = SRGBuilder()
            srg.policy_context = "Complex test"

            # Create predicates and aggregators
            p1 = srg.add_predicate("P1")
            p2 = srg.add_predicate("P2")
            p3 = srg.add_predicate("P3")

            agg1 = srg.add_aggregator(AllStrategy(), True, [p1, p2], "Agg1")
            _ = srg.add_aggregator(AtLeastStrategy(count=1), False, [p2, p3], "Agg2")

            outcome = srg.add_outcome("Success")

            # Create graph structure
            agg1_node = srg.add_node(agg1)
            outcome_node = srg.add_node(outcome)
            srg.add_edge(agg1_node, outcome_node, True)

            return srg.build()

        srg1 = create_complex_srg()
        srg2 = create_complex_srg()

        assert srg1 == srg2
        assert hash(srg1) == hash(srg2)

        # Test collection behavior
        srg_set = {srg1, srg2}
        assert len(srg_set) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
