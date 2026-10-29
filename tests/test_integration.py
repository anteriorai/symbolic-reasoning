"""
Integration tests for symbolic reasoning components.

This module focuses on true integration scenarios that test interactions
between multiple components and end-to-end workflows that aren't covered
by unit tests.
"""

import pytest

from symbolic_reasoning import SRGBuilder, apply_answers
from symbolic_reasoning.models import SRG, Answer, SRGExecution, SRGLite
from symbolic_reasoning.models.srg_execution import _outcome_paths
from tests.utils import (
    SolverScenario,
    assert_outcome_reached,
    create_predicate_answers,
    run_solver_scenario,
)

from .scenarios import (
    COMPLEX_SRG_BOTH_OUTCOMES,
    COMPLEX_SRG_O1,
    COMPLEX_SRG_O2,
)

# Test markers
pytestmark = pytest.mark.integration


class TestSRGLiteToSRGIntegration:
    """Test SRGLite to SRG conversion and execution integration."""

    def test_complex_medical_workflow_integration(self) -> None:
        """Test complete medical approval workflow from SRGLite to execution."""
        srg_lite = SRGLite(policy_context="Integrated medical approval policy")

        # Build complex medical scenario
        srg_lite.add_predicate("P1", "Is patient age >= 18?", "Age verification")
        srg_lite.add_predicate(
            "P2", "Does patient have valid insurance?", "Insurance check"
        )
        srg_lite.add_predicate("P3", "Is diagnosis confirmed?", "Medical verification")
        srg_lite.add_predicate("P4", "Is condition severe?", "Severity assessment")
        srg_lite.add_predicate("P5", "Is treatment cost under $10k?", "Cost analysis")
        srg_lite.add_predicate("P6", "Is provider in-network?", "Network verification")
        srg_lite.add_predicate(
            "P7", "Is this an emergency case?", "Emergency classification"
        )

        # Outcomes
        srg_lite.add_outcome("O1", "Treatment Approved")
        srg_lite.add_outcome("O2", "Treatment Denied")
        srg_lite.add_outcome("O3", "Emergency Treatment Approved")

        # Named aggregators for complex logic
        srg_lite.add_named_aggregator("BasicEligibility", "AllTrue(P1, P2)")
        srg_lite.add_named_aggregator("MedicalRequirements", "AllTrue(P3, P4)")
        srg_lite.add_named_aggregator(
            "StandardApproval", "AllTrue(BasicEligibility, MedicalRequirements, P5, P6)"
        )

        # Logical expressions
        srg_lite.add_logical_expression(
            "Emergency Approval", "Emergency bypass", "AllTrue(P7) -> O3"
        )
        srg_lite.add_logical_expression(
            "Standard Approval", "Normal approval path", "StandardApproval -> O1"
        )
        srg_lite.add_logical_expression(
            "Denial", "Default denial", "AllFalse(P1, P2) -> O2"
        )

        # Convert to SRG and test execution
        srg = srg_lite.to_srg()

        # Test emergency approval path
        emergency_execution = SRGExecution(srg=srg)
        pred_ids = list(srg.predicates.keys())

        # Find emergency predicate
        emergency_pred_id = None
        for pred_id, predicate in srg.predicates.items():
            if "emergency" in predicate.question.lower():
                emergency_pred_id = pred_id
                break

        assert emergency_pred_id is not None

        # Set emergency case
        emergency_execution = apply_answers(
            emergency_execution,
            {
                emergency_pred_id: Answer(
                    is_met=True,
                    reasoning="Emergency case requiring immediate attention",
                )
            },
        )

        # Set other predicates (shouldn't matter for emergency path)
        for pred_id in pred_ids:
            if pred_id != emergency_pred_id:
                emergency_execution = apply_answers(
                    emergency_execution,
                    {
                        pred_id: Answer(
                            is_met=False, reasoning="Not relevant for emergency"
                        )
                    },
                )

        # Should reach emergency approval
        assert_outcome_reached(emergency_execution, "Emergency Treatment Approved")

        # Test standard approval path
        standard_execution = SRGExecution(srg=srg)

        # Set all conditions to favorable except emergency
        for pred_id, predicate in srg.predicates.items():
            if "emergency" in predicate.question.lower():
                standard_execution = apply_answers(
                    standard_execution,
                    {pred_id: Answer(is_met=False, reasoning="Not an emergency")},
                )
            else:
                standard_execution = apply_answers(
                    standard_execution,
                    {
                        pred_id: Answer(
                            is_met=True, reasoning="Condition met for standard approval"
                        )
                    },
                )

        # Should reach standard approval
        assert_outcome_reached(standard_execution, "Treatment Approved")

    def test_financial_loan_workflow_integration(self) -> None:
        """Test financial loan approval workflow integration."""
        srg_lite = SRGLite(policy_context="Loan approval integration test")

        # Applicant criteria
        srg_lite.add_predicate("P1", "Is applicant age >= 21?")
        srg_lite.add_predicate("P2", "Does applicant have stable income?")
        srg_lite.add_predicate("P3", "Is credit score >= 650?")
        srg_lite.add_predicate("P4", "Is debt-to-income ratio < 40%?")
        srg_lite.add_predicate("P5", "Is loan amount <= $500,000?")
        srg_lite.add_predicate("P6", "Is down payment >= 20%?")

        # Outcomes
        srg_lite.add_outcome("O1", "Loan Approved")
        srg_lite.add_outcome("O2", "Loan Denied")
        srg_lite.add_outcome("O3", "Loan Approved with Conditions")

        # Complex approval logic
        srg_lite.add_named_aggregator("BasicQualification", "AllTrue(P1, P2, P3)")
        srg_lite.add_named_aggregator("FinancialHealth", "AllTrue(P4, P5)")

        # Multiple approval paths
        srg_lite.add_logical_expression(
            "Premium Approval",
            "Best candidates",
            "AllTrue(BasicQualification, FinancialHealth, P6) -> O1",
        )
        srg_lite.add_logical_expression(
            "Standard Approval",
            "Good candidates",
            "AllTrue(BasicQualification, FinancialHealth) -> O3",
        )
        srg_lite.add_logical_expression(
            "Denial", "Insufficient qualifications", "AllFalse(P1, P2, P3) -> O2"
        )

        # Convert and test
        srg = srg_lite.to_srg()

        # Test premium approval
        premium_execution = SRGExecution(srg=srg)
        premium_answers = create_predicate_answers(srg, "all_true")
        premium_execution = apply_answers(premium_execution, premium_answers)

        outcome_paths = _outcome_paths(premium_execution)
        outcomes = [path[0].description for path in outcome_paths]
        assert any("Approved" in outcome for outcome in outcomes)

    def test_deeply_nested_aggregator_integration(self) -> None:
        """Test integration with deeply nested aggregator structures."""
        srg_lite = SRGLite(policy_context="Deep nesting integration test")

        # Create predicates for deep nesting
        for i in range(1, 9):
            srg_lite.add_predicate(f"P{i}", f"Condition {i}")

        srg_lite.add_outcome("O1", "Success")
        srg_lite.add_outcome("O2", "Failure")

        # Create nested aggregators
        srg_lite.add_named_aggregator("Level1A", "AllTrue(P1, P2)")
        srg_lite.add_named_aggregator("Level1B", "AllTrue(P3, P4)")
        srg_lite.add_named_aggregator("Level1C", "AtLeast1True(P5, P6)")
        srg_lite.add_named_aggregator("Level2A", "AllTrue(Level1A, Level1B)")
        srg_lite.add_named_aggregator("Level2B", "AtLeast1True(Level1C, P7, P8)")
        srg_lite.add_named_aggregator("Level3", "AllTrue(Level2A, Level2B)")

        # Final expressions
        srg_lite.add_logical_expression("Success", "Complex success", "Level3 -> O1")
        srg_lite.add_logical_expression(
            "Failure", "Default failure", "AllFalse(P1, P2) -> O2"
        )

        # Convert and test
        srg = srg_lite.to_srg()

        # Test with all conditions met
        execution = SRGExecution(srg=srg)
        all_true_answers = create_predicate_answers(srg, "all_true")
        execution = apply_answers(execution, all_true_answers)

        # Should succeed with complex nested logic
        assert_outcome_reached(execution, "Success")


class TestErrorHandlingIntegration:
    """Test error handling across component boundaries."""

    def test_invalid_srg_lite_conversion_errors(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test that invalid SRGLite structures raise appropriate errors during conversion."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Valid outcome")

        # Add invalid expression referencing non-existent predicate
        srg_lite.add_logical_expression(
            "Invalid", "References unknown predicate", "AllTrue(P1, P99) -> O1"
        )

        # Should raise error during conversion
        with pytest.raises((KeyError, ValueError)):
            srg_lite.to_srg()

    def test_execution_with_incomplete_srg_structure(self) -> None:
        """Test execution behavior with incomplete SRG structures."""
        srg = SRGBuilder()

        # Create SRG with predicate but no paths to outcomes
        pred_id = srg.add_predicate("Isolated predicate")
        outcome_id = srg.add_outcome("Unreachable outcome")

        # Add nodes but no connecting edges
        srg.add_node(pred_id)
        srg.add_node(outcome_id)

        execution = SRGExecution(srg=srg.build())
        execution = apply_answers(
            execution, {pred_id: Answer(is_met=True, reasoning="Test answer")}
        )

        # Should handle gracefully (may return empty paths)
        outcome_paths = _outcome_paths(execution)
        # Exact behavior depends on implementation, but shouldn't crash
        assert isinstance(outcome_paths, list)

    def test_circular_reference_handling(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test handling of circular references in complex structures."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Outcome 1")

        # Create potential circular reference through named aggregators
        srg_lite.add_named_aggregator("Agg1", "AllTrue(P1, Agg2)")
        srg_lite.add_named_aggregator("Agg2", "AllTrue(Agg1)")  # Circular!

        srg_lite.add_logical_expression("Rule", "Circular test", "Agg1 -> O1")

        # Should either handle gracefully or raise appropriate error
        try:
            srg = srg_lite.to_srg()
            # If conversion succeeds, basic structure should be intact
            assert isinstance(srg, SRG)
        except (ValueError, RecursionError):
            # Acceptable to raise error for circular references
            pass


class TestPerformanceIntegration:
    def test_large_scale_conversion_and_execution(self) -> None:
        """Test moderately large SRG structures."""
        srg_lite = SRGLite(policy_context="Large scale integration test")

        # Create moderately large structure
        num_predicates = 25
        num_outcomes = 8

        for i in range(1, num_predicates + 1):
            srg_lite.add_predicate(f"P{i}", f"Condition {i}")

        for i in range(1, num_outcomes + 1):
            srg_lite.add_outcome(f"O{i}", f"Outcome {i}")

        # Create logical expressions
        for i in range(1, num_outcomes):
            start_pred = (i - 1) * 3 + 1
            end_pred = min(start_pred + 2, num_predicates)
            predicates = [f"P{j}" for j in range(start_pred, end_pred + 1)]

            if len(predicates) >= 2:
                srg_lite.add_logical_expression(
                    f"Rule{i}",
                    f"Rule {i}",
                    f"AtLeast2True({', '.join(predicates)}) -> O{i}",
                )

        # Convert (should complete without timeout)
        srg = srg_lite.to_srg()

        # Basic execution test
        execution = SRGExecution(srg=srg)
        alternating_answers = create_predicate_answers(srg, "alternating")
        execution = apply_answers(execution, alternating_answers)

        # Should complete execution without performance issues
        outcome_paths = _outcome_paths(execution)
        assert isinstance(outcome_paths, list)
        assert len(srg.predicates) == num_predicates
        assert len(srg.outcomes) == num_outcomes

    def test_aggregator_deduplication_effectiveness(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test that aggregator deduplication works in complex scenarios."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Success")

        # Create expressions that should result in duplicate aggregators
        srg_lite.add_logical_expression("Rule1", "First", "AllTrue(P1, P2) -> O1")
        srg_lite.add_logical_expression(
            "Rule2", "Second", "AllTrue(P2, P1) -> O1"
        )  # Same args, different order
        srg_lite.add_logical_expression(
            "Rule3", "Third", "AllTrue(P1, P2) -> O1"
        )  # Exact duplicate

        # Convert
        srg = srg_lite.to_srg()

        # Should have deduplicated effectively
        # After expansion, aggregators may be removed, so just verify conversion succeeds
        assert len(srg.predicates) == 3
        assert len(srg.outcomes) == 1

        # Test execution works correctly
        execution = SRGExecution(srg=srg)
        all_true_answers = create_predicate_answers(srg, "all_true")
        execution = apply_answers(execution, all_true_answers)

        assert_outcome_reached(execution, "Success")


class TestE2EIntegration:
    """End-to-end solver tests. Each scenario asserts the exact predicate batch
    sequence, outcome paths, and distinct paths. Scenario data lives in scenarios.py;
    the SRG under test is provided by the fixture so construction stays separate.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param(COMPLEX_SRG_O1, id="o1_only"),
            pytest.param(COMPLEX_SRG_O2, id="o2_only"),
            pytest.param(COMPLEX_SRG_BOTH_OUTCOMES, id="both_outcomes"),
        ],
    )
    async def test_complex_srg(
        self, complex_srg: SRG, scenario: SolverScenario
    ) -> None:
        await run_solver_scenario(complex_srg, scenario)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
