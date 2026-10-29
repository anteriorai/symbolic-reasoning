"""
Integration tests for symbolic reasoning components.

This module focuses on true integration scenarios that test interactions
between multiple components and end-to-end workflows that aren't covered
by unit tests.
"""

import pytest

from symbolic_reasoning import SRGBuilder, apply_answers
from symbolic_reasoning.models import SRG, Answer, SRGExecution
from symbolic_reasoning.models.srg_execution import _outcome_paths
from tests.utils import (
    SolverScenario,
    run_solver_scenario,
)

from .scenarios import (
    COMPLEX_SRG_BOTH_OUTCOMES,
    COMPLEX_SRG_O1,
    COMPLEX_SRG_O2,
)

# Test markers
pytestmark = pytest.mark.integration


class TestErrorHandlingIntegration:
    """Test error handling across component boundaries."""

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
