"""Compile parsed SRG source into the runtime SRG model."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from symbolic_reasoning.gen.py.ast import (
    AggregatorDefinition,
    AllExpression,
    AnyExpression,
    AtLeastExpression,
    AtMostExpression,
    CitationDefinition,
    ExactlyExpression,
    Expression,
    Location,
    NoneExpression,
    NotExpression,
    OutcomeDefinition,
    PolicyContextDefinition,
    PredicateDefinition,
    ReferenceExpression,
    SourceFile,
)
from symbolic_reasoning.gen.py.ast import (
    Path as PathDefinition,
)
from symbolic_reasoning.models.srg import SRG, load_srg
from symbolic_reasoning.validation import is_graph_id

from .parser import parse_srg


class CompilerError(ValueError):
    """Raised when a syntactically valid policy cannot be compiled."""

    def __init__(self, message: str, loc: Location | None = None) -> None:
        super().__init__(message)
        self.loc = loc


# The largest whole number both JSON and the TypeScript compiler read back unchanged.
_MAX_COUNT = 2**53 - 1


def _check_aggregator(expression: Expression) -> None:
    """Reject what only a hand-built AST can hold; the parser never produces it."""
    node = expression.root
    if isinstance(node, ReferenceExpression):
        return
    if isinstance(node, NotExpression):
        if node.expr is None:
            raise CompilerError("'not' needs an expression", node.loc)
        return
    if not node.args:
        raise CompilerError("Aggregators require at least one argument", node.loc)
    if isinstance(node, AtLeastExpression | AtMostExpression | ExactlyExpression):
        minimum = 1 if isinstance(node, AtLeastExpression) else 0
        count = node.count
        if (
            isinstance(count, bool)
            or not isinstance(count, int | float)
            or not math.isfinite(count)
            or count != int(count)
            or not minimum <= count <= _MAX_COUNT
        ):
            raise CompilerError(
                f"'{node.type}' needs a whole-number count "
                f"from {minimum} to {_MAX_COUNT}",
                node.loc,
            )


class _Compiler:
    def __init__(self) -> None:
        self.predicates: dict[str, PredicateDefinition] = {}
        self.outcomes: dict[str, OutcomeDefinition] = {}
        self.named_aggregators: dict[str, AggregatorDefinition] = {}
        self.citations: dict[str, CitationDefinition] = {}
        self.paths: list[PathDefinition] = []
        self.node_counter = 1
        self.aggregator_counter = 1
        self.prefix_nodes: dict[tuple, str] = {}
        self.compiled_aggregators: dict[str, str] = {}
        self.resolving: list[str] = []
        self.kinds: dict[str, str] = {}

    def compile(self, ast: SourceFile) -> SRG:
        policy_context: str | None = None
        for wrapped_definition in ast.definitions:
            definition = wrapped_definition.root
            if isinstance(definition, PolicyContextDefinition):
                if policy_context is not None:
                    raise CompilerError(
                        "Duplicate policy_context declaration", definition.loc
                    )
                policy_context = definition.value
            elif isinstance(definition, PredicateDefinition):
                self._claim(definition, "predicate")
                self.predicates[definition.id] = definition
            elif isinstance(definition, OutcomeDefinition):
                self._claim(definition, "outcome")
                self.outcomes[definition.id] = definition
            elif isinstance(definition, AggregatorDefinition):
                self._claim(definition, "define")
                self.named_aggregators[definition.id] = definition
            elif isinstance(definition, CitationDefinition):
                if definition.id in self.citations:
                    raise CompilerError(
                        f"'{definition.id}' is already defined as a citation",
                        definition.loc,
                    )
                self.citations[definition.id] = definition
            else:
                self.paths.append(definition)

        # Citations may be declared after a cite, so check once all are known.
        for wrapped_definition in ast.definitions:
            cited: set[str] = set()
            for reference in (
                getattr(wrapped_definition.root, "citation_refs", None) or []
            ):
                if reference.id not in self.citations:
                    kind = (
                        "a predicate"
                        if reference.id in self.predicates
                        else "an outcome"
                        if reference.id in self.outcomes
                        else "a define"
                        if reference.id in self.named_aggregators
                        else None
                    )
                    raise CompilerError(
                        f"'{reference.id}' is {kind}; cite: takes citation ids"
                        if kind
                        else f"Citation '{reference.id}' is not defined",
                        reference.loc,
                    )
                if reference.id in cited:
                    raise CompilerError(
                        f"Citation '{reference.id}' is cited twice", reference.loc
                    )
                cited.add(reference.id)

        result: dict[str, Any] = {
            "predicates": {},
            "aggregators": {},
            "outcomes": {},
            "nodes": {"Root": {"id": "Root", "item_id": "Root"}},
            "edges": {},
            "policy_context": policy_context,
        }
        if self.citations:
            result["citations"] = {
                identifier: self._citation(citation)
                for identifier, citation in self.citations.items()
            }

        for identifier, predicate in self.predicates.items():
            value: dict[str, Any] = {
                "type": "Predicate",
                "id": identifier,
                "question": predicate.question,
            }
            if predicate.context:
                value["context"] = predicate.context
            self._add_common(value, predicate)
            result["predicates"][identifier] = value

        for identifier, outcome in self.outcomes.items():
            value = {
                "type": "Outcome",
                "id": identifier,
                "description": outcome.description,
            }
            self._add_common(value, outcome)
            result["outcomes"][identifier] = value

        for path in self.paths:
            self._compile_path(path, result)

        return load_srg(result)

    def _claim(
        self,
        definition: PredicateDefinition | OutcomeDefinition | AggregatorDefinition,
        kind: str,
    ) -> None:
        """Predicates, outcomes and defines share one namespace."""
        if definition.id == "root":
            raise CompilerError("'root' is reserved for the graph root", definition.loc)
        if is_graph_id(definition.id):
            raise CompilerError(
                f"'{definition.id}' is reserved for graph ids", definition.loc
            )
        if existing := self.kinds.get(definition.id):
            article = "an" if existing == "outcome" else "a"
            raise CompilerError(
                f"'{definition.id}' is already defined as {article} {existing}",
                definition.loc,
            )
        self.kinds[definition.id] = kind

    def _citation(self, citation: CitationDefinition) -> dict[str, Any]:
        value: dict[str, Any] = {"source_ref": citation.source_ref}
        if citation.filename:
            value["filename"] = citation.filename
        if citation.regions is not None:
            value["regions"] = [
                region.model_dump(mode="json") for region in citation.regions
            ]
        if citation.excerpt:
            value["excerpt"] = citation.excerpt
        if citation.metadata is not None:
            value["metadata"] = citation.metadata
        return value

    def _add_common(self, output: dict[str, Any], definition: Any) -> None:
        if definition.label:
            output["label"] = definition.label
        if definition.doc:
            output["doc"] = definition.doc
        if definition.citation_refs:
            output["citation_ids"] = [
                reference.id for reference in definition.citation_refs
            ]
        if definition.properties is not None:
            output["metadata"] = definition.properties

    def _compile_path(self, path: PathDefinition, result: dict[str, Any]) -> None:
        if not path.steps:
            raise CompilerError(f"Path '{path.id}' has no steps", path.loc)
        outcome_id = path.outcome_ref.id
        if outcome_id not in result["outcomes"]:
            raise CompilerError(
                f"Outcome '{outcome_id}' not found (referenced in path)",
                path.outcome_ref.loc,
            )
        outcome_node = next(
            (
                node
                for node in result["nodes"].values()
                if node["item_id"] == outcome_id
            ),
            None,
        )
        if outcome_node is None:
            outcome_node = {"id": self._next_node_id(), "item_id": outcome_id}
            result["nodes"][outcome_node["id"]] = outcome_node

        conditions = path.conditions
        if conditions is None:
            conditions = [True] * len(path.steps)
        if len(conditions) != len(path.steps):
            raise CompilerError(
                "Path conditions must contain one boolean per step", path.loc
            )
        starts_with_root = (
            isinstance(path.steps[0].root, ReferenceExpression)
            and path.steps[0].root.id == "root"
        )
        if starts_with_root and not conditions[0]:
            raise CompilerError(
                "root is always true, so it never takes a false edge",
                path.steps[0].root.loc,
            )
        source = "Root"
        start = 1 if starts_with_root else 0
        for index in range(start, len(path.steps)):
            condition = conditions[index - 1] if index else True
            target = self._compile_expression(
                path.steps[index], result, source, condition
            )
            self._add_edge(result, source, target, condition)
            source = target
        self._add_edge(result, source, outcome_node["id"], conditions[-1])

    @staticmethod
    def _add_edge(
        result: dict[str, Any], source: str, target: str, condition: bool
    ) -> None:
        # Opposite conditions can connect the same pair of nodes.
        edge_id = f"E_{source}->{target}" + ("" if condition else ":false")
        result["edges"][edge_id] = {
            "source": source,
            "target": target,
            "condition": condition,
        }

    @staticmethod
    def _expression_key(expression: Expression) -> tuple:
        """Compare source expressions without their source locations."""
        _check_aggregator(expression)
        node = expression.root
        if isinstance(node, ReferenceExpression):
            return (node.type, node.id)
        if isinstance(node, NotExpression):
            return (node.type, _Compiler._expression_key(node.expr))
        return (
            node.type,
            getattr(node, "count", None),
            tuple(_Compiler._expression_key(arg) for arg in node.args),
        )

    def _compile_expression(
        self,
        expression: Expression,
        result: dict[str, Any],
        source: str,
        condition: bool,
    ) -> str:
        # The parent already identifies the entire prefix. Include edge polarity
        # to keep positive and negative continuations separate after divergence.
        key = (source, condition, self._expression_key(expression))
        if key in self.prefix_nodes:
            return self.prefix_nodes[key]
        item_id = self._compile_expression_to_item_id(expression, result)
        node_id = self._next_node_id()
        result["nodes"][node_id] = {"id": node_id, "item_id": item_id}
        self.prefix_nodes[key] = node_id
        return node_id

    def _compile_expression_to_item_id(
        self,
        expression: Expression,
        result: dict[str, Any],
        *,
        name: str = "",
        label: str | None = None,
        doc: str | None = None,
        properties: dict[str, Any] | None = None,
        citation_ids: list[str] | None = None,
    ) -> str:
        node = expression.root
        if isinstance(node, ReferenceExpression):
            if node.id == "root":
                raise CompilerError("root can only start a path", node.loc)
            if node.id in result["predicates"]:
                return node.id
            named = self.named_aggregators.get(node.id)
            if named is None:
                raise CompilerError(
                    f"Reference '{node.id}' not found (not a predicate or named aggregator)",
                    node.loc,
                )
            if node.id in self.compiled_aggregators:
                return self.compiled_aggregators[node.id]
            if node.id in self.resolving:
                cycle = [*self.resolving[self.resolving.index(node.id) :], node.id]
                raise CompilerError(
                    f"'{node.id}' refers to itself: {' -> '.join(cycle)}", node.loc
                )
            self.resolving.append(node.id)
            expression = named.expression
            if isinstance(expression.root, ReferenceExpression):
                # A define is always its own aggregator, so its name and
                # annotations reach the graph.
                expression = Expression(
                    root=AllExpression(
                        type="all", args=[expression], loc=expression.root.loc
                    )
                )
            item_id = self._compile_expression_to_item_id(
                expression,
                result,
                name=node.id,
                label=named.label,
                doc=named.doc,
                properties=named.properties,
                citation_ids=(
                    [reference.id for reference in named.citation_refs]
                    if named.citation_refs
                    else None
                ),
            )
            self.resolving.pop()
            self.compiled_aggregators[node.id] = item_id
            return item_id

        _check_aggregator(expression)
        if isinstance(node, NotExpression):
            arguments = [node.expr]
            strategy: dict[str, Any] = {"type": "AllStrategy"}
            truth_value = False
        else:
            arguments = node.args
            truth_value = not isinstance(node, NoneExpression)
            if isinstance(node, AllExpression | NoneExpression):
                strategy = {"type": "AllStrategy"}
            elif isinstance(node, AnyExpression):
                strategy = {"type": "AtLeastStrategy", "count": 1}
            elif isinstance(node, AtLeastExpression):
                strategy = {"type": "AtLeastStrategy", "count": node.count}
            elif isinstance(node, AtMostExpression):
                strategy = {"type": "AtMostStrategy", "count": node.count}
            else:
                strategy = {"type": "ExactlyStrategy", "count": node.count}

        return self._create_aggregator(
            result,
            strategy,
            truth_value,
            [
                self._compile_expression_to_item_id(argument, result)
                for argument in arguments
            ],
            name,
            label,
            doc,
            citation_ids,
            properties,
        )

    def _create_aggregator(
        self,
        result: dict[str, Any],
        strategy: dict[str, Any],
        truth_value: bool,
        argument_ids: list[str],
        name: str,
        label: str | None,
        doc: str | None,
        citation_ids: list[str] | None,
        properties: dict[str, Any] | None,
    ) -> str:
        if not argument_ids:
            raise CompilerError("Aggregators require at least one argument")
        identifier = self._next_aggregator_id()
        value: dict[str, Any] = {
            "type": "Aggregator",
            "id": identifier,
            "name": name,
            "truth_value": truth_value,
            "strategy": strategy,
            "argument_ids": argument_ids,
        }
        if label:
            value["label"] = label
        if doc:
            value["doc"] = doc
        if citation_ids:
            value["citation_ids"] = citation_ids
        if properties is not None:
            value["metadata"] = properties
        result["aggregators"][identifier] = value
        return identifier

    def _next_node_id(self) -> str:
        identifier = f"SN_{self.node_counter}"
        self.node_counter += 1
        return identifier

    def _next_aggregator_id(self) -> str:
        identifier = f"A{self.aggregator_counter}"
        self.aggregator_counter += 1
        return identifier


def compile_srg_ast(ast: SourceFile) -> SRG:
    """Compile a parsed SRG AST to the runtime model."""
    return _Compiler().compile(ast)


def compile_srg_string(source: str) -> SRG:
    """Compile SRG source text without requiring Node.js or native extensions."""
    return compile_srg_ast(parse_srg(source))


def compile_srg_file(path: str | Path) -> SRG:
    """Compile an UTF-8 encoded ``.srg`` file."""
    return compile_srg_string(Path(path).read_text(encoding="utf-8"))
