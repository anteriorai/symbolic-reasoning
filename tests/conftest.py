"""
Shared test fixtures and utilities for the symbolic reasoning test suite.

This module provides reusable fixtures that eliminate redundancy across test files
and follow DRY principles for common test scenarios.
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from symbolic_reasoning import SRGBuilder, compile_srg_file
from symbolic_reasoning.models import (
    AllStrategy,
    Answer,
    AtLeastStrategy,
    AtMostStrategy,
    ExactlyStrategy,
)
from symbolic_reasoning.models.srg import SRG
from symbolic_reasoning.models.srg_lite import SRGLite
from symbolic_reasoning.solvers.requests import OracleRequest
from tests.scenarios import make_complex_srg

# ============================================================================
# Basic SRG Fixtures
# ============================================================================


@pytest.fixture
def simple_srg() -> SRG:
    """Simple SRG with 2 predicates and 1 outcome for basic testing."""
    srg = SRGBuilder()
    srg.policy_context = "Simple test policy"

    p1_id = srg.add_predicate("Is condition A met?")
    p2_id = srg.add_predicate("Is condition B met?")
    outcome_id = srg.add_outcome("Success")

    # Create simple chain: Root -> P1 -> P2 -> Outcome
    p1_node = srg.add_node(p1_id)
    p2_node = srg.add_node(p2_id)
    outcome_node = srg.add_node(outcome_id)

    srg.add_edge("Root", p1_node, condition=True)
    srg.add_edge(p1_node, p2_node, condition=True)
    srg.add_edge(p2_node, outcome_node, condition=True)

    return srg.build()


@pytest.fixture
def branching_srg() -> SRG:
    """SRG with branching paths for testing different outcomes."""
    srg = SRGBuilder()
    srg.policy_context = "Branching test policy"

    p1_id = srg.add_predicate("Main condition")
    approved_id = srg.add_outcome("Approved")
    denied_id = srg.add_outcome("Denied")

    p1_node = srg.add_node(p1_id)
    approved_node = srg.add_node(approved_id)
    denied_node = srg.add_node(denied_id)

    srg.add_edge("Root", p1_node, condition=True)
    srg.add_edge(p1_node, approved_node, condition=True)
    srg.add_edge(p1_node, denied_node, condition=False)

    return srg.build()


@pytest.fixture
def medical_approval_srg() -> SRG:
    """Complex medical treatment approval SRG for integration testing."""
    srg = SRGBuilder()
    srg.policy_context = "Medical treatment approval policy"

    # Basic eligibility
    age_id = srg.add_predicate("Is patient age >= 18?", "Age verification")
    insurance_id = srg.add_predicate(
        "Does patient have valid insurance?", "Insurance check"
    )

    # Medical requirements
    diagnosis_id = srg.add_predicate("Is diagnosis confirmed?", "Medical verification")
    severity_id = srg.add_predicate("Is condition severe?", "Severity assessment")

    # Cost and provider
    cost_id = srg.add_predicate("Is treatment cost under $10k?", "Cost analysis")
    _ = srg.add_predicate(
        "Is provider in-network?", "Network verification"
    )  # Used in complex workflow

    # Emergency
    emergency_id = srg.add_predicate(
        "Is this an emergency case?", "Emergency classification"
    )

    # Aggregators
    basic_agg_id = srg.add_aggregator(
        strategy=AllStrategy(),
        truth_value=True,
        argument_ids=[age_id, insurance_id],
        name="Basic Eligibility",
    )

    medical_agg_id = srg.add_aggregator(
        strategy=AllStrategy(),
        truth_value=True,
        argument_ids=[diagnosis_id, severity_id],
        name="Medical Requirements",
    )

    final_agg_id = srg.add_aggregator(
        strategy=AllStrategy(),
        truth_value=True,
        argument_ids=[basic_agg_id, medical_agg_id, cost_id],
        name="Final Decision",
    )

    # Outcomes
    approved_id = srg.add_outcome("Treatment Approved")
    denied_id = srg.add_outcome("Treatment Denied")
    emergency_approved_id = srg.add_outcome("Emergency Treatment Approved")

    # Build graph structure
    emergency_node = srg.add_node(emergency_id)
    final_node = srg.add_node(final_agg_id)
    approved_node = srg.add_node(approved_id)
    denied_node = srg.add_node(denied_id)
    emergency_approved_node = srg.add_node(emergency_approved_id)

    # Connect root to source nodes
    srg.add_edge("Root", emergency_node, condition=True)
    srg.add_edge("Root", final_node, condition=True)

    # Emergency bypass
    srg.add_edge(emergency_node, emergency_approved_node, condition=True)

    # Normal approval flow
    srg.add_edge(final_node, approved_node, condition=True)
    srg.add_edge(final_node, denied_node, condition=False)

    return srg.build()


# ============================================================================
# Short-circuiting SRG Fixtures
# ============================================================================


@pytest.fixture
def all_strategy_srg() -> SRG:
    """all(P1, P2, P3) → Approved / Denied."""
    srg = SRGBuilder()
    p1 = srg.add_predicate("P1")
    p2 = srg.add_predicate("P2")
    p3 = srg.add_predicate("P3")

    agg = srg.add_aggregator(
        strategy=AllStrategy(),
        truth_value=True,
        argument_ids=[p1, p2, p3],
    )
    approved = srg.add_outcome("Approved")
    denied = srg.add_outcome("Denied")
    agg_node = srg.add_node(agg)
    approved_node = srg.add_node(approved)
    denied_node = srg.add_node(denied)

    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, approved_node, condition=True)
    srg.add_edge(agg_node, denied_node, condition=False)

    return srg.build()


@pytest.fixture
def atleast_2_of_3_srg() -> SRG:
    """atleast(2, P1, P2, P3) → Pass."""
    srg = SRGBuilder()
    p1 = srg.add_predicate("P1")
    p2 = srg.add_predicate("P2")
    p3 = srg.add_predicate("P3")

    agg = srg.add_aggregator(
        strategy=AtLeastStrategy(count=2),
        truth_value=True,
        argument_ids=[p1, p2, p3],
    )
    outcome = srg.add_outcome("Pass")
    agg_node = srg.add_node(agg)
    outcome_node = srg.add_node(outcome)

    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, outcome_node, condition=True)

    return srg.build()


@pytest.fixture
def atleast_3_of_3_srg() -> SRG:
    """atleast(3, P1, P2, P3) → Pass / Fail."""
    srg = SRGBuilder()
    p1 = srg.add_predicate("P1")
    p2 = srg.add_predicate("P2")
    p3 = srg.add_predicate("P3")

    agg = srg.add_aggregator(
        strategy=AtLeastStrategy(count=3),
        truth_value=True,
        argument_ids=[p1, p2, p3],
    )
    outcome_pass = srg.add_outcome("Pass")
    outcome_fail = srg.add_outcome("Fail")
    agg_node = srg.add_node(agg)
    pass_node = srg.add_node(outcome_pass)
    fail_node = srg.add_node(outcome_fail)

    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, pass_node, condition=True)
    srg.add_edge(agg_node, fail_node, condition=False)

    return srg.build()


@pytest.fixture
def none_of_srg() -> SRG:
    """all(truth_value=False, [P1, P2, P3]) → Passed / Failed."""
    srg = SRGBuilder()
    p1 = srg.add_predicate("P1")
    p2 = srg.add_predicate("P2")
    p3 = srg.add_predicate("P3")

    agg = srg.add_aggregator(
        strategy=AllStrategy(),
        truth_value=False,
        argument_ids=[p1, p2, p3],
    )
    passed = srg.add_outcome("Passed")
    failed = srg.add_outcome("Failed")
    agg_node = srg.add_node(agg)
    passed_node = srg.add_node(passed)
    failed_node = srg.add_node(failed)

    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, passed_node, condition=True)
    srg.add_edge(agg_node, failed_node, condition=False)

    return srg.build()


@pytest.fixture
def negated_atleast_2_srg() -> SRG:
    """atleast(2, truth_value=False, [P1, P2, P3]) → Passed."""
    srg = SRGBuilder()
    p1 = srg.add_predicate("P1")
    p2 = srg.add_predicate("P2")
    p3 = srg.add_predicate("P3")

    agg = srg.add_aggregator(
        strategy=AtLeastStrategy(count=2),
        truth_value=False,
        argument_ids=[p1, p2, p3],
    )
    passed = srg.add_outcome("Passed")
    agg_node = srg.add_node(agg)
    passed_node = srg.add_node(passed)

    srg.add_edge("Root", agg_node, condition=True)
    srg.add_edge(agg_node, passed_node, condition=True)

    return srg.build()


@pytest.fixture
def complex_srg() -> SRG:
    """Complex multi-strategy SRG fixture. See scenarios.make_complex_srg for structure."""
    return make_complex_srg()


# ============================================================================
# Answer Fixtures
# ============================================================================


@pytest.fixture
def standard_answers() -> dict[str, Answer]:
    """Standard set of answers for common test scenarios."""
    return {
        "all_true": Answer(is_met=True, reasoning="All conditions met"),
        "all_false": Answer(is_met=False, reasoning="Conditions not met"),
        "age_valid": Answer(is_met=True, reasoning="Patient is 25 years old"),
        "insurance_valid": Answer(is_met=True, reasoning="Valid insurance coverage"),
        "insurance_invalid": Answer(is_met=False, reasoning="Insurance expired"),
        "diagnosis_confirmed": Answer(
            is_met=True, reasoning="Diagnosis confirmed by specialist"
        ),
        "condition_severe": Answer(
            is_met=True, reasoning="Condition requires immediate treatment"
        ),
        "cost_acceptable": Answer(is_met=True, reasoning="Treatment cost is $8,000"),
        "provider_in_network": Answer(is_met=True, reasoning="Provider is in-network"),
        "emergency_case": Answer(
            is_met=True, reasoning="Emergency requiring immediate attention"
        ),
        "not_emergency": Answer(is_met=False, reasoning="Standard case, not emergency"),
    }


# ============================================================================
# Mock Oracle Fixtures
# ============================================================================


@pytest.fixture
def tracking_mock_oracle() -> MagicMock:
    """Mock oracle that tracks calls and returns configurable responses."""
    mock = MagicMock()
    mock.call_tracker = []

    def oracle_func(
        request: OracleRequest,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Answer]:
        predicate_requests = request.predicate_requests
        predicates = [r.predicate for r in predicate_requests]
        mock.call_tracker.append(
            {
                "predicates": [p.id for p in predicates],
                "contextual_predicates": {
                    r.predicate.id: [
                        (step.predicate_id, step.is_met)
                        for step in r.contextual_predicates
                    ]
                    for r in predicate_requests
                },
                "policy_context": request.policy_context,
                "args": args,
                "kwargs": kwargs,
            }
        )

        # Default to all true unless configured otherwise
        responses = getattr(mock, "responses", {})
        return {
            p.id: responses.get(
                p.id, Answer(is_met=True, reasoning=f"Default answer for {p.id}")
            )
            for p in predicates
        }

    mock.side_effect = oracle_func
    return mock


@pytest.fixture
def async_mock_oracle() -> AsyncMock:
    """Async mock oracle for testing async solver functionality."""
    mock = AsyncMock()
    mock.call_tracker = []

    async def async_oracle_func(
        request: OracleRequest,
        *_args: Any,
        **_kwargs: Any,
    ) -> dict[str, Answer]:
        predicate_requests = request.predicate_requests
        predicates = [r.predicate for r in predicate_requests]
        mock.call_tracker.append(
            {
                "predicates": [p.id for p in predicates],
                "contextual_predicates": {
                    r.predicate.id: [
                        (step.predicate_id, step.is_met)
                        for step in r.contextual_predicates
                    ]
                    for r in predicate_requests
                },
                "policy_context": request.policy_context,
            }
        )

        # Default to all true unless configured otherwise
        responses = getattr(mock, "responses", {})
        return {
            p.id: responses.get(
                p.id, Answer(is_met=True, reasoning=f"Async answer for {p.id}")
            )
            for p in predicates
        }

    mock.side_effect = async_oracle_func
    return mock


# ============================================================================
# SRGLite Fixtures
# ============================================================================


@pytest.fixture
def complex_srg_lite() -> SRGLite:
    """Complex SRGLite with named aggregators for advanced testing."""
    srg_lite = SRGLite(policy_context="Complex test policy")

    # Predicates
    for i in range(1, 7):
        srg_lite.add_predicate(f"P{i}", f"Condition {i}")

    # Outcomes
    srg_lite.add_outcome("O1", "Approved")
    srg_lite.add_outcome("O2", "Denied")
    srg_lite.add_outcome("O3", "Under Review")

    # Named aggregators
    srg_lite.add_named_aggregator("BasicChecks", "AllTrue(P1, P2, P3)")
    srg_lite.add_named_aggregator("AdvancedChecks", "AtLeast2True(P4, P5, P6)")

    # Logical expressions
    srg_lite.add_logical_expression(
        "Approval", "Standard approval", "AllTrue(BasicChecks, AdvancedChecks) -> O1"
    )
    srg_lite.add_logical_expression(
        "Review", "Partial approval", "AllTrue(BasicChecks) -> O3"
    )
    srg_lite.add_logical_expression(
        "Denial", "Default denial", "AllFalse(P1, P2) -> O2"
    )

    return srg_lite


# ============================================================================
# Aggregator Strategy Fixtures
# ============================================================================


@pytest.fixture
def aggregator_strategies() -> dict[str, Any]:
    """Common aggregator strategies for testing."""
    return {
        "all_2": AllStrategy(),
        "all_3": AllStrategy(),
        "atleast_1": AtLeastStrategy(count=1),
        "atleast_2": AtLeastStrategy(count=2),
        "atmost_1": AtMostStrategy(count=1),
        "atmost_2": AtMostStrategy(count=2),
        "exactly_1": ExactlyStrategy(count=1),
        "exactly_2": ExactlyStrategy(count=2),
    }


# ============================================================================
# Additional SRGLite Fixtures
# ============================================================================


@pytest.fixture
def basic_srg_lite_with_predicates() -> SRGLite:
    """SRGLite with basic predicates for testing predicate operations."""
    srg_lite = SRGLite(policy_context="Basic predicate test")

    srg_lite.add_predicate("P1", "Question 1")
    srg_lite.add_predicate("P2", "Question 2")
    srg_lite.add_predicate("P3", "Question 3")

    return srg_lite


@pytest.fixture
def srg_lite_with_named_aggregators() -> SRGLite:
    """SRGLite with named aggregators for testing aggregator functionality."""
    srg_lite = SRGLite(policy_context="Named aggregator test")

    srg_lite.add_predicate("P1", "Question 1")
    srg_lite.add_predicate("P2", "Question 2")
    srg_lite.add_predicate("P3", "Question 3")

    srg_lite.add_named_aggregator("BasicCheck", "AllTrue(P1, P2)")
    srg_lite.add_named_aggregator("AlternativeCheck", "AtLeast1True(P1, P2)")

    return srg_lite


@pytest.fixture
def comprehensive_srg_lite() -> SRGLite:
    """Comprehensive SRGLite with all elements for testing text format conversion."""
    srg_lite = SRGLite(policy_context="Comprehensive test")

    # Predicates with and without context
    srg_lite.add_predicate("P1", "Question 1")
    srg_lite.add_predicate("P2", "Question 2", "Context for P2")
    srg_lite.add_predicate("P3", "Question 3", "Context for P3")

    # Outcomes
    srg_lite.add_outcome("O1", "Outcome 1")
    srg_lite.add_outcome("O2", "Outcome 2")

    # Named aggregators
    srg_lite.add_named_aggregator("Check1", "AllTrue(P1, P2)")
    srg_lite.add_named_aggregator("Check2", "AtLeast1True(P2, P3)")

    # Logical expressions
    srg_lite.add_logical_expression("Rule1", "First rule", "Check1 -> O1")
    srg_lite.add_logical_expression("Rule2", "Second rule", "Check2 -> O2")

    return srg_lite


@pytest.fixture
def underwriting_policy() -> SRG:
    """Load the shared underwriting input policy without an SDK or builder."""
    policy = Path(__file__).parents[1] / "examples/data/underwriting/policy.srg"
    return compile_srg_file(policy)
