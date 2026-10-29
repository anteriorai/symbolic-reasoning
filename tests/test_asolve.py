"""
Auto solver tests.

This module focuses on core auto solver behavior:
1. Basic solver functionality with different SRG structures
2. Oracle interaction patterns and contextual predicate accumulation
3. Path execution scenarios (approval, denial, emergency)
4. Async oracle compatibility

Tests use minimal mocking and focus on solver behavior rather than infrastructure.
"""

import asyncio
import functools
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from symbolic_reasoning import SRGBuilder, is_resolved, reasoning_trace
from symbolic_reasoning.models import SRG, Answer, Coverage, evaluate_symbol
from symbolic_reasoning.models.srg_execution import _outcome_paths
from symbolic_reasoning.solvers.auto import asolve
from symbolic_reasoning.solvers.requests import OracleRequest

# Test markers
pytestmark = pytest.mark.asyncio


class TestAutoSolverCore:
    """Test core auto solver functionality."""

    async def test_simple_approval_path(
        self, simple_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test basic approval path execution."""
        # Configure oracle to approve all conditions
        pred_ids = list(simple_srg.predicates.keys())
        responses = {
            pred_ids[0]: Answer(is_met=True, reasoning="First condition met"),
            pred_ids[1]: Answer(is_met=True, reasoning="Second condition met"),
        }
        tracking_mock_oracle.responses = responses

        # Execute solver
        execution = await asolve(simple_srg, tracking_mock_oracle)

        # Verify execution results
        assert evaluate_symbol(execution, pred_ids[0]) is True
        assert evaluate_symbol(execution, pred_ids[1]) is True

        # Verify oracle was called correctly
        assert len(tracking_mock_oracle.call_tracker) >= 1

        # Should reach success outcome
        outcome_paths = _outcome_paths(execution)
        outcomes = [path[0].description for path in outcome_paths]
        assert "Success" in outcomes

    async def test_branching_path_execution(
        self, branching_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test execution with branching paths."""
        pred_ids = list(branching_srg.predicates.keys())

        # Test approval path
        responses = {pred_ids[0]: Answer(is_met=True, reasoning="Condition approved")}
        tracking_mock_oracle.responses = responses

        execution = await asolve(branching_srg, tracking_mock_oracle)

        outcome_paths = _outcome_paths(execution)
        outcomes = [path[0].description for path in outcome_paths]
        assert "Approved" in outcomes
        assert "Denied" not in outcomes

    async def test_denial_path_execution(
        self, branching_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test execution leading to denial."""
        pred_ids = list(branching_srg.predicates.keys())

        # Test denial path
        responses = {pred_ids[0]: Answer(is_met=False, reasoning="Condition denied")}
        tracking_mock_oracle.responses = responses

        execution = await asolve(branching_srg, tracking_mock_oracle)

        outcome_paths = _outcome_paths(execution)
        outcomes = [path[0].description for path in outcome_paths]
        assert "Denied" in outcomes
        assert "Approved" not in outcomes

    async def test_medical_approval_workflow(
        self, medical_approval_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test complex medical approval workflow."""
        # Set up approval scenario (all conditions met except emergency)
        responses = {}
        for pred_id, predicate in medical_approval_srg.predicates.items():
            if "emergency" in predicate.question.lower():
                responses[pred_id] = Answer(is_met=False, reasoning="Not emergency")
            else:
                responses[pred_id] = Answer(is_met=True, reasoning="Condition met")

        tracking_mock_oracle.responses = responses

        execution = await asolve(medical_approval_srg, tracking_mock_oracle)

        # Should reach treatment approval
        outcome_paths = _outcome_paths(execution)
        outcomes = [path[0].description for path in outcome_paths]
        assert "Treatment Approved" in outcomes

    async def test_emergency_bypass_path(
        self, medical_approval_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test emergency case bypasses normal checks."""
        # Set up emergency scenario
        responses = {}
        for pred_id, predicate in medical_approval_srg.predicates.items():
            if "emergency" in predicate.question.lower():
                responses[pred_id] = Answer(is_met=True, reasoning="Emergency case")
            else:
                # Other conditions can be false - emergency should bypass
                responses[pred_id] = Answer(
                    is_met=False, reasoning="Not relevant for emergency"
                )

        tracking_mock_oracle.responses = responses

        execution = await asolve(medical_approval_srg, tracking_mock_oracle)

        # Should reach emergency approval
        outcome_paths = _outcome_paths(execution)
        outcomes = [path[0].description for path in outcome_paths]
        assert "Emergency Treatment Approved" in outcomes


class TestOracleInteraction:
    """Test oracle interaction patterns and contextual accumulation."""

    async def test_contextual_predicate_accumulation(
        self, simple_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test that contextual predicates accumulate correctly."""
        pred_ids = list(simple_srg.predicates.keys())
        responses = {
            pred_ids[0]: Answer(is_met=True, reasoning="First condition"),
            pred_ids[1]: Answer(is_met=True, reasoning="Second condition"),
        }
        tracking_mock_oracle.responses = responses

        await asolve(simple_srg, tracking_mock_oracle)

        # Verify contextual accumulation
        calls = tracking_mock_oracle.call_tracker
        assert len(calls) >= 2

        assert calls[0]["contextual_predicates"] == {pred_ids[0]: []}
        assert calls[1]["contextual_predicates"] == {pred_ids[1]: [(pred_ids[0], True)]}

    async def test_policy_context_propagation(
        self, simple_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test that policy context is passed to oracle."""
        pred_ids = list(simple_srg.predicates.keys())
        responses = {
            pred_id: Answer(is_met=True, reasoning="Test") for pred_id in pred_ids
        }
        tracking_mock_oracle.responses = responses

        await asolve(simple_srg, tracking_mock_oracle)

        # Verify policy context in all calls
        for call_info in tracking_mock_oracle.call_tracker:
            assert call_info["policy_context"] == simple_srg.policy_context

    async def test_oracle_arguments_are_bound_by_the_caller(
        self, simple_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Extra oracle arguments are bound with partial; asolve forwards none."""
        pred_ids = list(simple_srg.predicates.keys())
        responses = {
            pred_id: Answer(is_met=True, reasoning="Test") for pred_id in pred_ids
        }
        tracking_mock_oracle.responses = responses

        await asolve(
            simple_srg,
            functools.partial(tracking_mock_oracle, custom_param="test_value"),
        )

        for call_info in tracking_mock_oracle.call_tracker:
            assert call_info["kwargs"]["custom_param"] == "test_value"

    async def test_options_are_keyword_only(
        self, simple_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """A positional coverage is rejected rather than passed to the oracle."""
        with pytest.raises(TypeError):
            await asolve(simple_srg, tracking_mock_oracle, Coverage.REACHABLE)  # ty: ignore[too-many-positional-arguments]
        assert not tracking_mock_oracle.call_tracker

    async def test_async_oracle_compatibility(
        self, simple_srg: SRG, async_mock_oracle: AsyncMock
    ) -> None:
        """Test compatibility with async oracles."""
        pred_ids = list(simple_srg.predicates.keys())
        responses = {
            pred_id: Answer(is_met=True, reasoning="Async test") for pred_id in pred_ids
        }
        async_mock_oracle.responses = responses

        execution = await asolve(simple_srg, async_mock_oracle)

        # Verify execution completed successfully
        assert len(execution.answers) >= 1
        assert len(async_mock_oracle.call_tracker) >= 1

    async def test_oracle_response_validation(self, simple_srg: SRG) -> None:
        """Test that invalid oracle responses raise appropriate errors."""

        def bad_oracle(
            _request: OracleRequest, *_args: Any, **_kwargs: Any
        ) -> dict[str, Answer]:
            # Never answer what was asked, so the solve cannot advance
            return {}

        bad_oracle_mock = MagicMock()
        bad_oracle_mock.side_effect = bad_oracle

        with pytest.raises(ValueError, match="cannot advance"):
            await asolve(simple_srg, bad_oracle_mock)


class TestPredicateBatching:
    """Test predicate batching and deduplication behavior."""

    async def test_predicate_deduplication_within_batch(self) -> None:
        """Test that duplicate predicates are deduplicated within oracle calls."""
        srg = SRGBuilder()
        srg.policy_context = "Deduplication test"

        # Create shared predicate used by multiple nodes at same level
        shared_pred_id = srg.add_predicate("Shared condition")
        unique_pred_id = srg.add_predicate("Unique condition")
        outcome_id = srg.add_outcome("Result")

        # Create nodes that use same predicate (will be batched together)
        node1 = srg.add_node(shared_pred_id)
        node2 = srg.add_node(shared_pred_id)  # Duplicate
        node3 = srg.add_node(unique_pred_id)
        outcome_node = srg.add_node(outcome_id)

        srg.add_edge("Root", node1, condition=True)
        srg.add_edge("Root", node2, condition=True)
        srg.add_edge("Root", node3, condition=True)
        srg.add_edge(node1, outcome_node, condition=True)
        srg.add_edge(node2, outcome_node, condition=True)
        srg.add_edge(node3, outcome_node, condition=True)

        # Track oracle calls
        call_count: dict[str, int] = {}
        predicate_calls = []

        def tracking_oracle(
            request: OracleRequest, *_args: Any, **_kwargs: Any
        ) -> dict[str, Answer]:
            predicates = [r.predicate for r in request.predicate_requests]
            predicate_calls.append([p.id for p in predicates])
            for predicate in predicates:
                call_count[predicate.id] = call_count.get(predicate.id, 0) + 1
            return {
                p.id: Answer(is_met=True, reasoning=f"Answer for {p.id}")
                for p in predicates
            }

        tracking_oracle_mock = MagicMock()
        tracking_oracle_mock.side_effect = tracking_oracle

        await asolve(srg.build(), tracking_oracle_mock)

        # Verify shared predicate was only queried once despite multiple nodes
        assert call_count[shared_pred_id] == 1
        assert call_count[unique_pred_id] == 1

        # Verify deduplication within first batch
        first_call_predicates = predicate_calls[0]
        assert first_call_predicates.count(shared_pred_id) == 1

    async def test_predicate_caching_across_levels(self) -> None:
        """Test that predicate answers are cached across different execution levels."""
        srg = SRGBuilder()
        srg.policy_context = "Caching test"

        trigger_pred_id = srg.add_predicate("Trigger")
        shared_pred_id = srg.add_predicate("Shared condition")
        final_pred_id = srg.add_predicate("Final condition")
        outcome_id = srg.add_outcome("Result")

        # Create nodes at different levels
        trigger_node = srg.add_node(trigger_pred_id)  # Level 1
        shared_node_1 = srg.add_node(shared_pred_id)  # Level 2
        shared_node_2 = srg.add_node(shared_pred_id)  # Level 3 (reuse)
        final_node = srg.add_node(final_pred_id)  # Level 4
        outcome_node = srg.add_node(outcome_id)

        # Create chain to ensure different levels
        srg.add_edge("Root", trigger_node, condition=True)
        srg.add_edge(trigger_node, shared_node_1, condition=True)
        srg.add_edge(shared_node_1, shared_node_2, condition=True)
        srg.add_edge(shared_node_2, final_node, condition=True)
        srg.add_edge(final_node, outcome_node, condition=True)

        # Track calls
        call_count: dict[str, int] = {}

        def tracking_oracle(
            request: OracleRequest, *_args: Any, **_kwargs: Any
        ) -> dict[str, Answer]:
            predicates = [r.predicate for r in request.predicate_requests]
            for predicate in predicates:
                call_count[predicate.id] = call_count.get(predicate.id, 0) + 1
            return {
                p.id: Answer(is_met=True, reasoning=f"Answer for {p.id}")
                for p in predicates
            }

        tracking_oracle_mock = MagicMock()
        tracking_oracle_mock.side_effect = tracking_oracle

        await asolve(srg.build(), tracking_oracle_mock)

        # Shared predicate should only be queried once despite appearing at multiple levels
        assert call_count[shared_pred_id] == 1
        assert call_count[trigger_pred_id] == 1
        assert call_count[final_pred_id] == 1

    async def test_empty_predicate_batches(self) -> None:
        """Test behavior when nodes have no predicates."""
        srg = SRGBuilder()

        outcome_id = srg.add_outcome("Direct outcome")
        outcome_node = srg.add_node(outcome_id)

        srg.add_edge("Root", outcome_node, condition=True)

        call_tracker = []

        def tracking_oracle(
            request: OracleRequest, *_args: Any, **_kwargs: Any
        ) -> dict[str, Answer]:
            predicates = [r.predicate for r in request.predicate_requests]
            call_tracker.append([p.id for p in predicates])
            return {p.id: Answer(is_met=True, reasoning="test") for p in predicates}

        tracking_oracle_mock = MagicMock()
        tracking_oracle_mock.side_effect = tracking_oracle

        execution = await asolve(srg.build(), tracking_oracle_mock)

        # No oracle calls should be made for outcome-only SRG
        assert len(call_tracker) == 0
        assert len(execution.answers) == 0


class TestComplexScenarios:
    """Test complex solver scenarios."""

    async def test_parallel_path_execution(self) -> None:
        """Test execution with parallel paths that both lead to outcomes."""
        srg = SRGBuilder()
        srg.policy_context = "Parallel paths test"

        # Create parallel structure
        p1_id = srg.add_predicate("Path 1 condition")
        p2_id = srg.add_predicate("Path 2 condition")
        o1_id = srg.add_outcome("Outcome 1")
        o2_id = srg.add_outcome("Outcome 2")

        p1_node = srg.add_node(p1_id)
        p2_node = srg.add_node(p2_id)
        o1_node = srg.add_node(o1_id)
        o2_node = srg.add_node(o2_id)

        # Both predicates connect to both outcomes (parallel paths)
        srg.add_edge("Root", p1_node, condition=True)
        srg.add_edge("Root", p2_node, condition=True)
        srg.add_edge(p1_node, o1_node, condition=True)
        srg.add_edge(p2_node, o2_node, condition=True)

        # Track calls
        call_tracker = []

        def tracking_oracle(
            request: OracleRequest, *_args: Any, **_kwargs: Any
        ) -> dict[str, Answer]:
            predicates = [r.predicate for r in request.predicate_requests]
            call_tracker.append([p.id for p in predicates])
            return {
                p.id: Answer(is_met=True, reasoning=f"Answer for {p.id}")
                for p in predicates
            }

        tracking_oracle_mock = MagicMock()
        tracking_oracle_mock.side_effect = tracking_oracle

        execution = await asolve(srg.build(), tracking_oracle_mock)

        # Should process both parallel paths
        assert len(execution.answers) == 2
        assert p1_id in execution.answers
        assert p2_id in execution.answers

        # Should batch parallel predicates together
        assert len(call_tracker) == 1
        first_call = call_tracker[0]
        assert set(first_call) == {p1_id, p2_id}

    async def test_aggregator_argument_batching(
        self, medical_approval_srg: SRG, tracking_mock_oracle: MagicMock
    ) -> None:
        """Test that aggregator arguments are batched correctly."""
        # Set up responses for all predicates
        responses = {}
        for pred_id, predicate in medical_approval_srg.predicates.items():
            responses[pred_id] = Answer(
                is_met=True, reasoning=f"Answer for {predicate.question}"
            )

        tracking_mock_oracle.responses = responses

        await asolve(medical_approval_srg, tracking_mock_oracle)

        # Verify that oracle was called and batching occurred
        calls = tracking_mock_oracle.call_tracker
        assert len(calls) >= 1

        # Should have batched predicates together when possible
        total_predicates = sum(len(call["predicates"]) for call in calls)
        assert total_predicates >= 2  # Multiple predicates were processed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


@pytest.mark.parametrize("use_callable_object", [True, False])
async def test_oracle_awaitable_results(
    simple_srg: SRG, use_callable_object: bool
) -> None:
    """Protocol-compatible callables need not be async function objects."""
    calls: list[list[str]] = []

    def future_oracle(request: OracleRequest, /) -> asyncio.Future[dict[str, Answer]]:
        assert request.policy_context == simple_srg.policy_context
        requests = request.predicate_requests
        calls.append([r.predicate.id for r in requests])
        response: asyncio.Future[dict[str, Answer]] = (
            asyncio.get_running_loop().create_future()
        )
        response.set_result(
            {r.predicate.id: Answer(is_met=True, reasoning="awaited") for r in requests}
        )
        return response

    class CallableOracle:
        async def __call__(self, request: OracleRequest, /) -> dict[str, Answer]:
            return await future_oracle(request)

    oracle = CallableOracle() if use_callable_object else future_oracle
    execution = await asolve(simple_srg, oracle)
    assert is_resolved(execution)
    assert reasoning_trace(execution).outcome_paths
    assert {p for batch in calls for p in batch} == set(execution.answers)
    assert calls
