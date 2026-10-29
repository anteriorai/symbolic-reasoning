"""
SRGLite model tests.

This module focuses on SRGLite-specific functionality:
1. Text format conversion (to/from UI format)
2. Reference validation
3. Logical expression parsing
4. Named aggregator support
5. SRGLite-specific edge cases

Tests avoid redundant conversion scenarios covered in integration tests.
"""

import pytest

from symbolic_reasoning.models.srg_lite import (
    SRGLite,
    SRGLiteLogicalExpression,
)

# Test markers
pytestmark = pytest.mark.unit


class TestSRGLiteBasicOperations:
    """Test basic SRGLite construction and operations."""

    def test_srg_lite_creation(self) -> None:
        """Test SRGLite creation with context."""
        context = "Test policy context"
        srg_lite = SRGLite(policy_context=context)

        assert srg_lite.policy_context == context
        assert len(srg_lite.predicates) == 0
        assert len(srg_lite.outcomes) == 0
        assert len(srg_lite.named_aggregators) == 0
        assert len(srg_lite.logical_expressions) == 0

    def test_predicate_addition_with_context(self) -> None:
        """Test adding predicates with optional context."""
        srg_lite = SRGLite(policy_context="Context test")

        srg_lite.add_predicate("P1", "Question with context", "Important context")
        srg_lite.add_predicate("P2", "Question without context")
        srg_lite.add_predicate("P3", "Question with context", "Another context")

        assert len(srg_lite.predicates) == 3
        assert srg_lite.predicates["P1"].context == "Important context"
        assert srg_lite.predicates["P2"].context is None
        assert srg_lite.predicates["P3"].context == "Another context"

    def test_named_aggregator_management(
        self, srg_lite_with_named_aggregators: SRGLite
    ) -> None:
        """Test named aggregator addition and retrieval."""
        srg_lite = srg_lite_with_named_aggregators

        assert len(srg_lite.named_aggregators) == 2
        assert srg_lite.named_aggregators["BasicCheck"] == "AllTrue(P1, P2)"
        assert srg_lite.named_aggregators["AlternativeCheck"] == "AtLeast1True(P1, P2)"


class TestLogicalExpressionParsing:
    """Test logical expression functionality."""

    def test_logical_expression_parsing(self) -> None:
        """Test parsing of logical expressions."""
        expr = SRGLiteLogicalExpression(
            title="Test Rule",
            description="Test description",
            logical_expression="AllTrue(P1, P2, P3) -> O1",
        )

        assert expr.get_logical_condition() == "AllTrue(P1, P2, P3)"
        assert expr.get_target_outcome() == "O1"

    def test_complex_logical_expression(self) -> None:
        """Test parsing of complex logical expressions."""
        expr = SRGLiteLogicalExpression(
            title="Complex Rule",
            description="Complex test",
            logical_expression="AtLeast2True(P1, AllTrue(P2, P3), P4) -> O2",
        )

        condition = expr.get_logical_condition()
        target = expr.get_target_outcome()

        assert condition == "AtLeast2True(P1, AllTrue(P2, P3), P4)"
        assert target == "O2"

    def test_invalid_expression_formats(self) -> None:
        """Test handling of invalid expression formats."""
        # Only test expressions that actually raise ValueError
        invalid_expressions = [
            "AllTrue(P1, P2)",  # Missing arrow
            "",  # Empty expression
        ]

        for invalid_expr in invalid_expressions:
            expr = SRGLiteLogicalExpression(
                title="Invalid",
                description="Invalid test",
                logical_expression=invalid_expr,
            )

            with pytest.raises(ValueError, match="Invalid expression format"):
                expr.get_logical_condition()

            with pytest.raises(ValueError, match="Invalid expression format"):
                expr.get_target_outcome()

        # Test edge cases that don't raise errors but return empty/minimal parts
        edge_cases = [
            ("AllTrue() -> O1", "AllTrue()", "O1"),  # Empty aggregator
            ("AllTrue(P1) ->", "AllTrue(P1)", ""),  # Missing outcome
            ("-> O1", "", "O1"),  # Missing condition
        ]

        for expr_text, expected_condition, expected_outcome in edge_cases:
            expr = SRGLiteLogicalExpression(
                title="Edge case",
                description="Edge case test",
                logical_expression=expr_text,
            )

            assert expr.get_logical_condition() == expected_condition
            assert expr.get_target_outcome() == expected_outcome


class TestTextFormatConversion:
    """Test conversion to/from text format used by UI."""

    def test_to_text_format_comprehensive(
        self, comprehensive_srg_lite: SRGLite
    ) -> None:
        """Test comprehensive text format conversion."""
        srg_lite = comprehensive_srg_lite

        text_format = srg_lite.to_text_format()

        # Verify all sections are present
        assert "predicates" in text_format
        assert "outcomes" in text_format
        assert "outcome_paths" in text_format  # UI expects this key
        assert "named_aggregators" in text_format
        assert "context" in text_format

        # Check content format
        predicates_text = text_format["predicates"]
        assert "P1: Question 1" in predicates_text
        assert "P2: Question 2" in predicates_text
        assert "P3: Question 3" in predicates_text

        outcomes_text = text_format["outcomes"]
        assert "O1: Outcome 1" in outcomes_text
        assert "O2: Outcome 2" in outcomes_text

        named_agg_text = text_format["named_aggregators"]
        assert "Check1: AllTrue(P1, P2)" in named_agg_text
        assert "Check2: AtLeast1True(P2, P3)" in named_agg_text

        context_text = text_format["context"]
        assert "P2: Context for P2" in context_text
        assert "P3: Context for P3" in context_text
        assert "P1:" not in context_text  # P1 has no context

    def test_from_text_format_comprehensive(self) -> None:
        """Test creating SRGLite from comprehensive text format."""
        predicates_text = "P1: Question 1\nP2: Question 2\nP3: Question 3"
        outcomes_text = "O1: Outcome 1\nO2: Outcome 2"
        outcome_paths_text = "AllTrue(P1, P2) -> O1\nAtLeast1True(P2, P3) -> O2"
        named_aggregators_text = (
            "BasicCheck: AllTrue(P1, P2)\nAdvancedCheck: AtLeast1True(P2, P3)"
        )
        context_text = "P2: Important context\nP3: Another context"
        policy_context = "Comprehensive test policy"

        srg_lite = SRGLite.from_text_format(
            predicates_text=predicates_text,
            outcomes_text=outcomes_text,
            outcome_paths_text=outcome_paths_text,
            named_aggregators_text=named_aggregators_text,
            context_text=context_text,
            policy_context=policy_context,
        )

        # Verify predicates
        assert len(srg_lite.predicates) == 3
        assert srg_lite.predicates["P1"].question == "Question 1"
        assert srg_lite.predicates["P1"].context is None
        assert srg_lite.predicates["P2"].context == "Important context"
        assert srg_lite.predicates["P3"].context == "Another context"

        # Verify outcomes
        assert len(srg_lite.outcomes) == 2
        assert srg_lite.outcomes["O1"].description == "Outcome 1"

        # Verify named aggregators
        assert len(srg_lite.named_aggregators) == 2
        assert srg_lite.named_aggregators["BasicCheck"] == "AllTrue(P1, P2)"

        # Verify logical expressions
        assert len(srg_lite.logical_expressions) == 2
        assert (
            srg_lite.logical_expressions[0].logical_expression
            == "AllTrue(P1, P2) -> O1"
        )

        # Verify policy context
        assert srg_lite.policy_context == policy_context

    def test_roundtrip_text_conversion(self, comprehensive_srg_lite: SRGLite) -> None:
        """Test that to_text_format -> from_text_format preserves data."""
        original = comprehensive_srg_lite

        # Convert to text and back
        text_format = original.to_text_format()
        roundtrip = SRGLite.from_text_format(
            predicates_text=text_format["predicates"],
            outcomes_text=text_format["outcomes"],
            outcome_paths_text=text_format["outcome_paths"],
            named_aggregators_text=text_format["named_aggregators"],
            context_text=text_format["context"],
            policy_context=original.policy_context,
        )

        # Verify preservation
        assert len(roundtrip.predicates) == len(original.predicates)
        assert len(roundtrip.outcomes) == len(original.outcomes)
        assert len(roundtrip.named_aggregators) == len(original.named_aggregators)
        assert len(roundtrip.logical_expressions) == len(original.logical_expressions)
        assert roundtrip.policy_context == original.policy_context

        # Check specific content
        assert roundtrip.predicates["P1"].question == original.predicates["P1"].question
        assert roundtrip.predicates["P2"].context == original.predicates["P2"].context
        assert (
            roundtrip.named_aggregators["Check1"]
            == original.named_aggregators["Check1"]
        )

    def test_text_format_edge_cases(self) -> None:
        """Test text format handling with edge cases."""
        # Empty strings
        empty_srg_lite = SRGLite.from_text_format("", "", "")
        assert len(empty_srg_lite.predicates) == 0
        assert len(empty_srg_lite.outcomes) == 0
        assert len(empty_srg_lite.logical_expressions) == 0

        # Whitespace handling
        whitespace_predicates = "  P1  :  Question 1  \n  P2:Question 2\n\n"
        whitespace_outcomes = "\n  O1: Outcome 1  \n"

        whitespace_srg_lite = SRGLite.from_text_format(
            whitespace_predicates, whitespace_outcomes, ""
        )

        # Should handle whitespace gracefully
        assert len(whitespace_srg_lite.predicates) >= 1
        assert len(whitespace_srg_lite.outcomes) == 1

        # Malformed lines should be ignored
        malformed_predicates = "P1: Question 1\nMalformed line\nP2: Question 2"
        malformed_srg_lite = SRGLite.from_text_format(
            malformed_predicates, "O1: Outcome 1", ""
        )

        assert len(malformed_srg_lite.predicates) == 2  # Malformed line ignored


class TestReferenceValidation:
    """Test SRGLite reference validation functionality."""

    def test_valid_references(self) -> None:
        """Test validation with all valid references."""
        srg_lite = SRGLite(policy_context="Expression test")

        srg_lite.add_predicate("P1", "Question 1")
        srg_lite.add_predicate("P2", "Question 2")
        srg_lite.add_predicate("P3", "Question 3")

        srg_lite.add_outcome("O1", "Outcome 1")
        srg_lite.add_outcome("O2", "Outcome 2")

        srg_lite.add_logical_expression("Rule1", "First rule", "AllTrue(P1, P2) -> O1")
        srg_lite.add_logical_expression(
            "Rule2", "Second rule", "AllFalse(P1, P2) -> O2"
        )

        # Add a named aggregator and expression to complete the valid structure
        srg_lite.add_named_aggregator("Check", "AllTrue(P1, P2)")
        srg_lite.add_logical_expression("Rule", "Test rule", "Check -> O1")

        errors = srg_lite.validate_references()
        assert len(errors) == 0

    def test_invalid_predicate_references(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test validation catches invalid predicate references."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Outcome 1")

        # Invalid predicate in expression
        srg_lite.add_logical_expression("BadRule", "Bad", "AllTrue(P1, P99) -> O1")

        errors = srg_lite.validate_references()
        assert len(errors) == 1
        assert "Unknown predicate reference 'P99'" in errors[0]

    def test_invalid_outcome_references(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test validation catches invalid outcome references."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Outcome 1")

        # Invalid outcome in expression
        srg_lite.add_logical_expression("BadRule", "Bad", "AllTrue(P1) -> O99")

        errors = srg_lite.validate_references()
        assert len(errors) == 1
        assert "Unknown outcome reference 'O99'" in errors[0]

    def test_invalid_named_aggregator_references(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test validation catches invalid references in named aggregators."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Outcome 1")

        # Invalid predicate in named aggregator
        srg_lite.add_named_aggregator("BadCheck", "AllTrue(P1, P99)")
        srg_lite.add_logical_expression("Rule", "Test", "BadCheck -> O1")

        errors = srg_lite.validate_references()
        assert len(errors) == 1
        assert "Unknown predicate reference 'P99'" in errors[0]
        assert "Named aggregator 'BadCheck'" in errors[0]

    def test_multiple_validation_errors(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test validation reports multiple errors."""
        srg_lite = basic_srg_lite_with_predicates

        srg_lite.add_outcome("O1", "Outcome 1")

        # Multiple invalid references
        srg_lite.add_logical_expression("BadRule1", "Bad", "AllTrue(P1, P99) -> O1")
        srg_lite.add_logical_expression("BadRule2", "Bad", "AllTrue(P1) -> O99")

        errors = srg_lite.validate_references()
        assert len(errors) == 2
        assert any("P99" in error for error in errors)
        assert any("O99" in error for error in errors)


class TestSRGLiteFactoryMethods:
    """Test SRGLite factory methods."""

    def test_from_dicts_basic(self) -> None:
        """Test creating SRGLite from dictionaries."""
        predicates = {"P1": "Question 1", "P2": "Question 2"}
        outcomes = {"O1": "Outcome 1", "O2": "Outcome 2"}
        logical_expressions = [
            {
                "title": "Rule 1",
                "description": "First rule",
                "logical_expression": "AllTrue(P1, P2) -> O1",
            },
            {
                "title": "Rule 2",
                "description": "Second rule",
                "logical_expression": "AllFalse(P1, P2) -> O2",
            },
        ]

        srg_lite = SRGLite.from_dicts(predicates, outcomes, logical_expressions)

        assert len(srg_lite.predicates) == 2
        assert len(srg_lite.outcomes) == 2
        assert len(srg_lite.logical_expressions) == 2

        assert srg_lite.predicates["P1"].question == "Question 1"
        assert srg_lite.outcomes["O1"].description == "Outcome 1"
        assert srg_lite.logical_expressions[0].title == "Rule 1"

    def test_from_dicts_with_named_aggregators(
        self, basic_srg_lite_with_predicates: SRGLite
    ) -> None:
        """Test creating SRGLite from dicts, then adding named aggregators."""
        # Create from dicts first
        predicates = {"P1": "Question 1", "P2": "Question 2"}
        outcomes = {"O1": "Outcome 1"}
        logical_expressions = [
            {
                "title": "Rule 1",
                "description": "Using named aggregator",
                "logical_expression": "AllTrue(P1, P2) -> O1",
            }
        ]

        srg_lite = SRGLite.from_dicts(predicates, outcomes, logical_expressions)

        # Add named aggregator after creation
        srg_lite.add_named_aggregator("BasicCheck", "AllTrue(P1, P2)")

        assert len(srg_lite.named_aggregators) == 1
        assert srg_lite.named_aggregators["BasicCheck"] == "AllTrue(P1, P2)"


class TestSRGLiteEdgeCases:
    """Test SRGLite edge cases and error conditions."""

    def test_empty_srg_lite(self) -> None:
        """Test behavior with empty SRGLite."""
        empty_srg_lite = SRGLite()

        # Should handle empty state gracefully
        text_format = empty_srg_lite.to_text_format()
        assert text_format["predicates"] == ""
        assert text_format["outcomes"] == ""
        assert text_format["outcome_paths"] == ""

        errors = empty_srg_lite.validate_references()
        assert len(errors) == 0

    def test_unicode_content_handling(self) -> None:
        """Test handling of unicode content."""
        srg_lite = SRGLite()

        # Unicode in predicate and outcome
        srg_lite.add_predicate("P1", "Question with unicode: 你好世界 🌍")
        srg_lite.add_outcome("O1", "Outcome with unicode: Здравствуй мир ✓")
        srg_lite.add_logical_expression(
            "Unicode", "Unicode test: 测试", "AllTrue(P1) -> O1"
        )

        # Should handle unicode gracefully
        text_format = srg_lite.to_text_format()
        assert "你好世界" in text_format["predicates"]
        assert "Здравствуй мир" in text_format["outcomes"]

        # Roundtrip should preserve unicode
        roundtrip = SRGLite.from_text_format(
            text_format["predicates"],
            text_format["outcomes"],
            text_format["outcome_paths"],
        )

        assert "你好世界" in roundtrip.predicates["P1"].question
        assert "Здравствуй мир" in roundtrip.outcomes["O1"].description

    def test_special_characters_in_content(self) -> None:
        """Test handling of special characters in content."""
        srg_lite = SRGLite()

        srg_lite.add_predicate("P1", "Question with special chars: @#$%^&*()")
        srg_lite.add_outcome("O1", "Outcome with special chars: []{}|\\")
        srg_lite.add_logical_expression("Special", "Special test", "AllTrue(P1) -> O1")

        # Should preserve special characters
        text_format = srg_lite.to_text_format()
        assert "@#$%^&*()" in text_format["predicates"]
        assert "[]{}|\\" in text_format["outcomes"]

    def test_duplicate_ids_handling(self) -> None:
        """Test handling of duplicate IDs."""
        srg_lite = SRGLite()

        # Add predicate with same ID twice (should overwrite)
        srg_lite.add_predicate("P1", "First question")
        srg_lite.add_predicate("P1", "Second question")  # Overwrites

        assert len(srg_lite.predicates) == 1
        assert srg_lite.predicates["P1"].question == "Second question"

        # Same for outcomes
        srg_lite.add_outcome("O1", "First outcome")
        srg_lite.add_outcome("O1", "Second outcome")  # Overwrites

        assert len(srg_lite.outcomes) == 1
        assert srg_lite.outcomes["O1"].description == "Second outcome"


class TestSRGLiteConversion:
    """Test SRGLite conversion to SRG."""

    def test_predicate_ids_consistent(self) -> None:
        """Test that predicate IDs remain consistent after conversion."""
        srg_lite = SRGLite(policy_context="Conversion test")

        # Add predicates that do not start at P1
        srg_lite.add_predicate("P2", "Question 1")
        srg_lite.add_predicate("P5", "Question 2")
        srg_lite.add_predicate("P10", "Question 3")

        srg_lite.add_outcome("O3", "Outcome 1")
        srg_lite.add_logical_expression(
            "Rule1", "First rule", "AllTrue(P2, P5, P10) -> O3"
        )
        srg = srg_lite.to_srg()

        assert list(srg.predicates) == ["P2", "P5", "P10"]
        assert list(srg.outcomes) == ["O3"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestUndecidableArguments:
    """An outcome is never decided, so it cannot be an aggregator argument."""

    def test_outcome_argument_is_rejected(self) -> None:
        srg_lite = SRGLite.from_text_format(
            predicates_text="P1: Is the member eligible?",
            outcomes_text="O1: Approved\nO2: Escalate",
            outcome_paths_text="AllTrue(P1) -> O1\nAllTrue(P1, O1) -> O2",
        )

        with pytest.raises(ValueError, match="'O1' as an argument"):
            srg_lite.to_srg()

    def test_predicate_and_aggregator_arguments_are_accepted(self) -> None:
        srg = SRGLite.from_text_format(
            predicates_text="P1: Is the member eligible?\nP2: Is it urgent?",
            outcomes_text="O1: Approved",
            outcome_paths_text="AllTrue(P1, AtLeast1True(P1, P2)) -> O1",
        ).to_srg()

        assert len(srg.aggregators) == 2
