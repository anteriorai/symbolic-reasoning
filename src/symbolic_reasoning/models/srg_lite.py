"""
SRGLite - Lightweight representation of Symbolic Reasoning Graph components.

This module provides a schema for representing predicates, outcomes, and outcome paths
in a lightweight format that can be easily serialized and converted to a full SRG.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from symbolic_reasoning.gen.py.srg import (
    AllStrategy,
    AtLeastStrategy,
    AtMostStrategy,
    ExactlyStrategy,
)

from .srg import ROOT_ID, SRG, SRGBuilder


class SRGLitePredicate(BaseModel):
    """Lightweight representation of a predicate."""

    id: str
    question: str
    context: str | None = None


class SRGLiteOutcome(BaseModel):
    """Lightweight representation of an outcome."""

    id: str
    description: str


class SRGLiteLogicalExpression(BaseModel):
    """Lightweight representation of a logical expression."""

    title: str
    description: str
    logical_expression: str

    def get_target_outcome(self) -> str:
        """Extract the target outcome ID from the logical expression."""
        if "->" not in self.logical_expression:
            raise ValueError(f"Invalid expression format: {self.logical_expression}")
        return self.logical_expression.split("->")[1].strip()

    def get_logical_condition(self) -> str:
        """Extract the logical condition from the expression."""
        if "->" not in self.logical_expression:
            raise ValueError(f"Invalid expression format: {self.logical_expression}")
        return self.logical_expression.split("->")[0].strip()


class SRGLite(BaseModel):
    """
    SRGLite - Lightweight representation of a Symbolic Reasoning Graph.

    This schema represents the core components needed to construct an SRG:
    - Predicates: The questions/conditions to be evaluated
    - Outcomes: The possible results/decisions
    - Logical Expressions: The logical expressions mapping predicates to outcomes
    - Policy Context: General guidance applicable to the entire policy/guideline
    """

    predicates: dict[str, SRGLitePredicate] = Field(default_factory=dict)
    outcomes: dict[str, SRGLiteOutcome] = Field(default_factory=dict)
    named_aggregators: dict[str, str] = Field(default_factory=dict)
    logical_expressions: list[SRGLiteLogicalExpression] = Field(default_factory=list)
    policy_context: str | None = Field(default=None)

    @classmethod
    def from_dicts(
        cls,
        predicates: dict[str, str],
        outcomes: dict[str, str],
        logical_expressions: list[dict],
    ) -> SRGLite:
        """
        Create an SRGLite from dictionary representations.

        Args:
            predicates: Dict mapping predicate IDs to question strings
            outcomes: Dict mapping outcome IDs to description strings
            logical_expressions: List of logical expression dictionaries with title, description, logical_expression
        """
        lite_predicates = {
            pred_id: SRGLitePredicate(id=pred_id, question=question)
            for pred_id, question in predicates.items()
        }

        lite_outcomes = {
            outcome_id: SRGLiteOutcome(id=outcome_id, description=description)
            for outcome_id, description in outcomes.items()
        }

        lite_paths = [
            SRGLiteLogicalExpression(
                title=path.get("title", ""),
                description=path.get("description", ""),
                logical_expression=path.get("logical_expression", ""),
            )
            for path in logical_expressions
        ]

        return cls(
            predicates=lite_predicates,
            outcomes=lite_outcomes,
            logical_expressions=lite_paths,
        )

    def add_predicate(
        self, pred_id: str, question: str, context: str | None = None
    ) -> None:
        """Add a predicate to the SRGLite."""
        self.predicates[pred_id] = SRGLitePredicate(
            id=pred_id,
            question=question,
            context=context,
        )

    def add_outcome(self, outcome_id: str, description: str) -> None:
        """Add an outcome to the SRGLite."""
        self.outcomes[outcome_id] = SRGLiteOutcome(
            id=outcome_id,
            description=description,
        )

    def add_logical_expression(
        self, title: str, description: str, logical_expression: str
    ) -> None:
        """Add a logical expression to the SRGLite."""
        self.logical_expressions.append(
            SRGLiteLogicalExpression(
                title=title,
                description=description,
                logical_expression=logical_expression,
            )
        )

    def add_named_aggregator(self, name: str, expression: str) -> None:
        """Add a named aggregator to the SRGLite."""
        self.named_aggregators[name] = expression

    def to_srg(self) -> SRG:
        """
        Convert this lightweight representation to a full SRG.

        This method contains the logic previously in the parse() function
        to build the complete SRG structure with nodes, edges, and aggregators.
        """
        srg = SRGBuilder()
        srg.policy_context = self.policy_context
        known_ids = set()

        # Add predicates to SRG
        for pred_id, predicate in self.predicates.items():
            srg.add_predicate(predicate.question, predicate.context, id=pred_id)
            known_ids.add(pred_id)

        # Add outcomes to SRG
        for outcome_id, outcome in self.outcomes.items():
            srg.add_outcome(outcome.description, id=outcome_id)
            known_ids.add(outcome_id)

        # Helper functions for parsing logical expressions
        def _split_args(s: str) -> list[str]:
            """Split arguments while respecting nested parentheses."""
            args: list[str] = []
            buf = ""
            depth = 0
            for ch in s:
                if ch == "(":
                    depth += 1
                    buf += ch
                elif ch == ")":
                    depth -= 1
                    buf += ch
                elif ch == "," and depth == 0:
                    args.append(buf.strip())
                    buf = ""
                else:
                    buf += ch
            if buf.strip():
                args.append(buf.strip())
            return args

        memo: dict[str, str] = {}

        def _parse_expression(expr: str, name: str = "") -> str:
            """
            Recursively parse a logical expression part.
            Can be a predicate, a named aggregator, or a full aggregator function.
            Returns the ID of the corresponding SRG item.
            """
            expr = expr.strip()
            if expr in memo:
                return memo[expr]

            # Case 1: Named Aggregator
            if expr in self.named_aggregators:
                result = _parse_expression(self.named_aggregators[expr], name=expr)
                memo[expr] = result
                return result

            # Case 2: Predicate
            if expr in known_ids:
                return expr

            # Case 3: Aggregator function
            m = re.match(
                r"^(?P<op>All|AtLeast|AtMost|Exactly)(?P<count>\d*)(?P<truth>True|False)\((?P<args>.*)\)$",
                expr,
            )
            if m:
                op = m.group("op")
                count_str = m.group("count")
                truth = m.group("truth")
                arg_str = m.group("args")
                truth_value = truth == "True"

                parts = _split_args(arg_str)
                arg_ids: list[str] = [_parse_expression(part) for part in parts]

                if op.lower() == "all":
                    strategy: (
                        AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy
                    ) = AllStrategy()
                elif op.lower().startswith("atleast"):
                    count_val = int(count_str)
                    if count_val <= 0:
                        raise ValueError(
                            f"AtLeast strategy count must be positive, got {count_val}"
                        )
                    strategy = AtLeastStrategy(count=count_val)
                elif op.lower().startswith("atmost"):
                    count_val = int(count_str)
                    if count_val < 0:
                        raise ValueError(
                            f"AtMost strategy count cannot be negative, got {count_val}"
                        )
                    strategy = AtMostStrategy(count=count_val)
                elif op.lower().startswith("exactly"):
                    count_val = int(count_str)
                    if count_val < 0:
                        raise ValueError(
                            f"Exactly strategy count cannot be negative, got {count_val}"
                        )
                    strategy = ExactlyStrategy(count=count_val)
                else:
                    raise ValueError(f"Unknown aggregator operator: {op}")

                agg_id = srg.add_aggregator(
                    strategy=strategy,
                    truth_value=truth_value,
                    argument_ids=arg_ids,
                    name=name,
                )
                memo[expr] = agg_id
                return agg_id

            raise ValueError(f"Cannot parse expression: '{expr}'")

        # Process logical expressions
        outcome_node_map: dict[str, str] = {}

        for path in self.logical_expressions:
            expr = path.logical_expression
            if "->" not in expr:
                raise ValueError(f"Invalid expression format - missing '->': {expr}")
            if not expr.split("->")[0].strip():
                raise ValueError(f"Invalid expression format - empty condition: {expr}")
            if not expr.split("->")[1].strip():
                raise ValueError(f"Invalid expression format - empty outcome: {expr}")

            lhs, rhs = expr.split("->")
            lhs_stripped = lhs.strip()

            # Validate that LHS is not a bare predicate - must be an aggregator function
            if lhs_stripped in known_ids and lhs_stripped in self.predicates:
                raise ValueError(
                    f"Invalid expression format - bare predicate '{lhs_stripped}' must be wrapped in an aggregator function (e.g., AllTrue({lhs_stripped})): {expr}"
                )

            top_agg_id = _parse_expression(lhs_stripped)
            top_agg_node_id = srg.add_node(top_agg_id)

            outcome_id = rhs.strip()
            # Check if we already have a node for this outcome
            if outcome_id in outcome_node_map:
                outcome_node_id = outcome_node_map[outcome_id]
            else:
                outcome_node_id = srg.add_node(outcome_id)
                outcome_node_map[outcome_id] = outcome_node_id

            srg.add_edge(source=top_agg_node_id, target=outcome_node_id, condition=True)

        # Connect Root to all source nodes (nodes with no incoming edges)
        all_nodes = set(srg.nodes.keys())
        all_nodes.discard(ROOT_ID)  # Exclude Root itself
        target_nodes = {edge.target for edge in srg.edges.values()}
        source_nodes = all_nodes - target_nodes

        for node_id in source_nodes:
            srg.add_edge(ROOT_ID, node_id, condition=True)

        return srg.build()

    def validate_references(self) -> list[str]:
        """
        Validate that all predicate and outcome references in logical expressions are valid.

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Combine all expressions for checking
        all_expressions_with_source = [
            (f"Logical expression '{p.logical_expression}'", p.logical_expression)
            for p in self.logical_expressions
        ] + [
            (f"Named aggregator '{name}'", expr)
            for name, expr in self.named_aggregators.items()
        ]

        for source, expr in all_expressions_with_source:
            # Check for predicate references
            predicate_refs = re.findall(r"P\d+", expr)
            errors.extend(
                f"{source}: Unknown predicate reference '{ref}'"
                for ref in predicate_refs
                if ref not in self.predicates
            )

            # Check for outcome references (only in logical expressions)
            if "->" in expr:
                outcome_refs = re.findall(r"O\d+", expr.split("->")[1])
                errors.extend(
                    f"{source}: Unknown outcome reference '{ref}'"
                    for ref in outcome_refs
                    if ref not in self.outcomes
                )

        return errors

    def to_text_format(self) -> dict[str, str]:
        """
        Convert to text format compatible with the UI.

        Returns:
            Dictionary with 'predicates', 'outcomes', 'logical_expressions', and 'context' keys
        """
        predicates_text = "\n".join(
            [f"{pred_id}: {pred.question}" for pred_id, pred in self.predicates.items()]
        )

        outcomes_text = "\n".join(
            [
                f"{outcome_id}: {outcome.description}"
                for outcome_id, outcome in self.outcomes.items()
            ]
        )

        logical_expressions_text = "\n".join(
            [path.logical_expression for path in self.logical_expressions]
        )

        named_aggregators_text = "\n".join(
            [
                f"{name}: {expression}"
                for name, expression in self.named_aggregators.items()
            ]
        )

        # Generate context text only for predicates that have context
        context_text = "\n".join(
            [
                f"{pred_id}: {pred.context}"
                for pred_id, pred in self.predicates.items()
                if pred.context
            ]
        )

        return {
            "predicates": predicates_text,
            "outcomes": outcomes_text,
            "outcome_paths": logical_expressions_text,  # UI expects outcome_paths key
            "named_aggregators": named_aggregators_text,
            "context": context_text,
        }

    @classmethod
    def from_text_format(
        cls,
        predicates_text: str,
        outcomes_text: str,
        outcome_paths_text: str,  # UI passes outcome_paths, but we store as logical_expressions internally
        named_aggregators_text: str = "",
        context_text: str = "",
        policy_context: str | None = None,
    ) -> SRGLite:
        """
        Create an SRGLite from text format (as used in the UI).

        Args:
            predicates_text: Text with format "P1: Question\\nP2: Question\\n..."
            outcomes_text: Text with format "O1: Description\\nO2: Description\\n..."
            outcome_paths_text: Text with format "AllTrue(P1, P2) -> O1\\n..." (UI terminology for logical expressions)
            named_aggregators_text: Text with format "MyAgg: AllTrue(P1, P2)\\n..."
            context_text: Optional text with format "P1: Context\\nP2: Context\\n..."
            policy_context: Optional general policy guidance text
        """
        srg_lite = cls()
        srg_lite.policy_context = policy_context

        # Parse context into a dictionary
        context_dict = {}
        if context_text.strip():
            for line in context_text.strip().split("\n"):
                if line.strip():
                    match = re.match(r"^(P\d+):\s*(.+)$", line.strip())
                    if match:
                        pred_id, context = match.groups()
                        context_dict[pred_id] = context.strip()

        # Parse predicates
        for line in predicates_text.strip().split("\n"):
            if line.strip():
                match = re.match(r"^(P\d+):\s*(.+)$", line.strip())
                if match:
                    pred_id, question = match.groups()
                    context = context_dict.get(pred_id)
                    srg_lite.add_predicate(pred_id, question, context)

        # Parse outcomes
        for line in outcomes_text.strip().split("\n"):
            if line.strip():
                match = re.match(r"^(O\d+):\s*(.+)$", line.strip())
                if match:
                    outcome_id, description = match.groups()
                    srg_lite.add_outcome(outcome_id, description)

        # Parse named aggregators
        if named_aggregators_text.strip():
            for line in named_aggregators_text.strip().split("\n"):
                if line.strip():
                    match = re.match(
                        r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.+)$", line.strip()
                    )
                    if match:
                        name, expression = match.groups()
                        srg_lite.add_named_aggregator(name.strip(), expression.strip())

        # Parse logical expressions (from outcome_paths_text)
        for line in outcome_paths_text.strip().split("\n"):
            if line.strip() and "->" in line:
                srg_lite.add_logical_expression(
                    title="Generated Path",
                    description="Path from text input",
                    logical_expression=line.strip(),
                )

        return srg_lite
