from __future__ import annotations

import json
from typing import Any

from pydantic import (
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    model_validator,
)

from symbolic_reasoning.gen.py.srg import (
    SRG as SRGSchema,
)
from symbolic_reasoning.gen.py.srg import (
    Aggregator,
    AllStrategy,
    AtLeastStrategy,
    AtMostStrategy,
    Edge,
    ExactlyStrategy,
    Node,
    Outcome,
    Predicate,
    Strategy,
)
from symbolic_reasoning.validation import (
    ROOT_ID,
    SRGValidationError,
    is_graph_id,
    validate_srg,
)


class SRG(SRGSchema):
    """
    A validated, read-only reasoning graph.

    Construct one with ``load_srg()``, ``SRGBuilder.build()``, or a compiler;
    each runs ``validate_srg``. To change a graph, edit a builder from
    ``SRGBuilder.from_srg()`` and build again.
    """

    @model_validator(mode="after")
    def _validate_structure(self) -> SRG:
        validate_srg(self)
        return self

    def __eq__(self, other: object) -> bool:
        """Compare two SRG objects for structural equality."""
        if not isinstance(other, SRG):
            return NotImplemented

        # Compare edges structurally (content, not dict ordering)
        if len(self.edges) != len(other.edges):
            return False

        for edge_key, edge in self.edges.items():
            if edge_key not in other.edges:
                return False
            other_edge = other.edges[edge_key]
            if (
                edge.source != other_edge.source
                or edge.target != other_edge.target
                or edge.condition != other_edge.condition
            ):
                return False

        # Compare nodes by content
        if len(self.nodes) != len(other.nodes):
            return False

        for node_id, node in self.nodes.items():
            if node_id not in other.nodes:
                return False
            other_node = other.nodes[node_id]
            if node.item_id != other_node.item_id:
                return False

        # Compare predicates by content, not just ID
        if len(self.predicates) != len(other.predicates):
            return False

        for pred_id, pred in self.predicates.items():
            if pred_id not in other.predicates:
                return False
            other_pred = other.predicates[pred_id]
            if (
                pred.question != other_pred.question
                or pred.context != other_pred.context
            ):
                return False

        # Compare aggregators by content
        if len(self.aggregators) != len(other.aggregators):
            return False

        for agg_id, agg in self.aggregators.items():
            if agg_id not in other.aggregators:
                return False
            other_agg = other.aggregators[agg_id]
            if (
                agg.name != other_agg.name
                or str(agg.strategy) != str(other_agg.strategy)
                or agg.truth_value != other_agg.truth_value
                or sorted(agg.argument_ids) != sorted(other_agg.argument_ids)
            ):
                return False

        # Compare outcomes by content
        if len(self.outcomes) != len(other.outcomes):
            return False

        for outcome_id, outcome in self.outcomes.items():
            if outcome_id not in other.outcomes:
                return False
            other_outcome = other.outcomes[outcome_id]
            if outcome.description != other_outcome.description:
                return False

        # Compare policy context
        return self.policy_context == other.policy_context

    def __hash__(self) -> int:
        """Compute hash for SRG objects based on structural content."""
        # Create a tuple of hashable components
        # For edges, we need to hash the content, not the dict itself
        edge_items = tuple(
            sorted(
                (edge_key, edge.source, edge.target, edge.condition)
                for edge_key, edge in self.edges.items()
            )
        )

        # Hash other components that are already hashable or can be made hashable
        nodes_items = tuple(
            sorted((node_id, node.item_id) for node_id, node in self.nodes.items())
        )

        predicates_items = tuple(
            sorted(
                (pred_id, pred.question, pred.context)
                for pred_id, pred in self.predicates.items()
            )
        )

        aggregators_items = tuple(
            sorted(
                (
                    agg_id,
                    agg.name,
                    str(agg.strategy),
                    agg.truth_value,
                    tuple(sorted(agg.argument_ids)),
                )
                for agg_id, agg in self.aggregators.items()
            )
        )

        outcomes_items = tuple(
            sorted(
                (outcome_id, outcome.description)
                for outcome_id, outcome in self.outcomes.items()
            )
        )

        return hash(
            (
                edge_items,
                nodes_items,
                predicates_items,
                aggregators_items,
                outcomes_items,
                self.policy_context,
            )
        )


class SRGBuilder(SRGSchema):
    """
    Mutable draft of an SRG. ``build()`` validates it into a read-only ``SRG``.

    ID Generation Strategy:
        IDs are generated lazily by scanning existing entities to find the next available number.
        This eliminates state synchronization issues and works correctly after deserialization.
        Auto-generated IDs follow the pattern: P1, P2, ... / A1, A2, ... / O1, O2, ... / SN1, SN2, ...
        Pass ``id=`` to ``add_predicate``, ``add_aggregator`` or ``add_outcome`` to choose one instead.
    """

    model_config = ConfigDict(frozen=False)

    predicates: dict[str, Predicate] = Field(default_factory=dict)
    aggregators: dict[str, Aggregator] = Field(default_factory=dict)
    outcomes: dict[str, Outcome] = Field(default_factory=dict)
    nodes: dict[str, Node] = Field(
        default_factory=lambda: {ROOT_ID: Node(id=ROOT_ID, item_id=ROOT_ID)}
    )
    edges: dict[str, Edge] = Field(default_factory=dict)

    # Hash-based lookup for aggregator signatures - used for deduplication
    _aggregator_signatures: dict[str, str] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """
        Initialize aggregator signature cache after model construction.

        Called automatically by Pydantic after __init__ and after deserialization.
        Rebuilds the signature cache for aggregator deduplication.
        """
        for agg_id, agg in self.aggregators.items():
            self._aggregator_signatures[self._get_aggregator_signature(agg)] = agg_id

    @classmethod
    def from_srg(cls, srg: SRG) -> SRGBuilder:
        """Create a draft holding a copy of an existing graph."""
        return cls.model_validate(srg.model_dump())

    def build(self) -> SRG:
        """Validate the draft and return it as a read-only ``SRG``."""
        return load_srg(self.model_dump())

    def _next_id(self, prefix: str) -> str:
        """
        Generate the next ``{prefix}{number}`` ID not used by any node or symbol.

        Scans every store, not just the one the ID is for, so a generated ID
        never shadows a custom ID elsewhere. Stateless, so it works correctly
        after deserialization.
        """
        taken = [
            int(item_id[len(prefix) :])
            for store in (self.nodes, self.predicates, self.aggregators, self.outcomes)
            for item_id in store
            if item_id.startswith(prefix) and item_id[len(prefix) :].isdigit()
        ]
        return f"{prefix}{max(taken, default=0) + 1}"

    def _generate_node_id(self) -> str:
        return self._next_id("SN_")

    def _generate_predicate_id(self) -> str:
        return self._next_id("P")

    def _generate_aggregator_id(self) -> str:
        return self._next_id("A")

    def _generate_outcome_id(self) -> str:
        return self._next_id("O")

    def add_predicate(
        self,
        question: str,
        context: str | None = None,
        *,
        id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a predicate and return its ID, generated unless ``id`` is given."""
        predicate = Predicate(
            id=self._generate_predicate_id() if id is None else id,
            question=question,
            context=context,
            **kwargs,
        )
        return self._register_predicate(predicate)

    def _require_free_id(self, symbol_id: str, kind: str) -> None:
        """Reject a graph ID format, Root included, and an ID another kind of symbol uses."""
        if kind != "Aggregator" and is_graph_id(symbol_id):
            raise ValueError(f"{kind} ID '{symbol_id}' is reserved for graph IDs")
        for other, owner, store in (
            ("Predicate", "a predicate", self.predicates),
            ("Aggregator", "an aggregator", self.aggregators),
            ("Outcome", "an outcome", self.outcomes),
        ):
            if other != kind and symbol_id in store:
                raise ValueError(f"{kind} ID '{symbol_id}' is already used by {owner}")

    def _register_predicate(self, predicate: Predicate) -> str:
        """
        Add a predicate and return its ID.

        Raises:
            ValueError: If a predicate with this ID already exists, the ID
                takes a graph ID format such as Root, or another kind of symbol
                uses it
        """
        self._require_free_id(predicate.id, "Predicate")
        if predicate.id in self.predicates:
            raise ValueError(
                f"Predicate with ID '{predicate.id}' already exists. "
                f"Existing question: '{self.predicates[predicate.id].question}'"
            )
        self.predicates[predicate.id] = predicate
        return predicate.id

    @staticmethod
    def _get_aggregator_signature(aggregator: Aggregator) -> str:
        """Dedup key covering every field except the ID.

        Annotations, ``extra='allow'`` metadata and argument order are all
        author-visible, so all of them count. JSON keeps values that Python's
        ``==`` conflates (``True`` vs ``1``) apart.
        """
        return json.dumps(
            aggregator.model_dump(mode="json", exclude={"id"}), sort_keys=True
        )

    def _find_equivalent_aggregator(self, aggregator: Aggregator) -> str | None:
        """Find an existing aggregator indistinguishable from this one (ignoring ID)."""
        signature = self._get_aggregator_signature(aggregator)
        if self._still_has_signature(aggregator.id, signature):
            return aggregator.id
        cached = self._aggregator_signatures.get(signature)
        if cached is None or self._still_has_signature(cached, signature):
            return cached
        # Callers edited or removed aggregators since they were cached: re-index.
        self._aggregator_signatures = {
            self._get_aggregator_signature(existing): existing_id
            for existing_id, existing in self.aggregators.items()
        }
        return self._aggregator_signatures.get(signature)

    def _still_has_signature(self, aggregator_id: str, signature: str) -> bool:
        existing = self.aggregators.get(aggregator_id)
        return (
            existing is not None
            and self._get_aggregator_signature(existing) == signature
        )

    def add_aggregator(
        self,
        strategy: AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy,
        truth_value: bool,
        argument_ids: list[str],
        name: str = "",
        *,
        id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Add an aggregator and return its ID, generated unless ``id`` is given.

        An aggregator equal to an existing one returns that one's ID instead.
        """
        # Validate arguments
        if not argument_ids:
            raise ValueError(
                "Cannot create aggregator with empty argument_ids - aggregators must have at least one argument"
            )

        # The key needs the whole aggregator, so build first and dedup in register.
        aggregator = Aggregator(
            id=self._generate_aggregator_id() if id is None else id,
            strategy=Strategy(root=strategy),
            truth_value=truth_value,
            argument_ids=argument_ids,
            name=name,
            **kwargs,
        )
        return self._register_aggregator(aggregator)

    def _register_aggregator(self, aggregator: Aggregator) -> str:
        """
        Add an aggregator and return its ID, or the ID of an equal existing one.

        Raises:
            ValueError: If an argument is an outcome or Root, or an aggregator
                with this exact ID already exists but with different parameters
        """
        for argument_id in aggregator.argument_ids:
            if argument_id == ROOT_ID or argument_id in self.outcomes:
                raise ValueError(
                    f"Aggregator {aggregator.id!r} takes {argument_id!r} as an "
                    "argument, but only predicates and aggregators can be decided"
                )

        # Check if equivalent aggregator already exists
        existing_id = self._find_equivalent_aggregator(aggregator)
        if existing_id:
            return existing_id

        self._require_free_id(aggregator.id, "Aggregator")
        # Check for ID collision with different aggregator
        if aggregator.id in self.aggregators:
            raise ValueError(
                f"Aggregator with ID '{aggregator.id}' already exists with different parameters"
            )

        self.aggregators[aggregator.id] = aggregator

        # Store signature for future deduplication
        signature = self._get_aggregator_signature(aggregator)
        self._aggregator_signatures[signature] = aggregator.id
        return aggregator.id

    def add_outcome(
        self, description: str, *, id: str | None = None, **kwargs: Any
    ) -> str:
        """Add an outcome and return its ID, generated unless ``id`` is given."""
        outcome = Outcome(
            id=self._generate_outcome_id() if id is None else id,
            description=description,
            **kwargs,
        )
        return self._register_outcome(outcome)

    def _register_outcome(self, outcome: Outcome) -> str:
        """
        Add an outcome and return its ID.

        Raises:
            ValueError: If an outcome with this ID already exists, the ID
                takes a graph ID format such as Root, another kind of symbol
                uses it, or an aggregator already takes this ID as an argument
        """
        self._require_free_id(outcome.id, "Outcome")
        if outcome.id in self.outcomes:
            raise ValueError(
                f"Outcome with ID '{outcome.id}' already exists. "
                f"Existing description: '{self.outcomes[outcome.id].description}'"
            )
        for aggregator in self.aggregators.values():
            if outcome.id in aggregator.argument_ids:
                raise ValueError(
                    f"Aggregator {aggregator.id!r} takes {outcome.id!r} as an "
                    "argument, but only predicates and aggregators can be decided"
                )
        self.outcomes[outcome.id] = outcome
        return outcome.id

    def _has_registered_symbol(self, item_id: str) -> bool:
        """Return whether an ID refers to a registered symbol."""
        return any(
            item_id in store
            for store in (self.predicates, self.aggregators, self.outcomes)
        )

    def add_node(self, item_id: str) -> str:
        """Add a node and return its ID."""
        if item_id == ROOT_ID:
            raise ValueError(
                "Only the 'Root' node can wrap Root; start other rules from it"
            )
        if not self._has_registered_symbol(item_id):
            raise ValueError(
                f"Cannot add node for unknown item ID '{item_id}'. "
                "Add/Register the predicate, aggregator, or outcome first."
            )
        node_id = self._generate_node_id()
        self.nodes[node_id] = Node(id=node_id, item_id=item_id)
        return node_id

    def add_edge(self, source: str, target: str, condition: bool = True) -> SRGBuilder:
        """Add a conditional edge, rejecting an identical transition.

        Opposite conditions may connect the same nodes. Existing edge IDs are
        preserved, including IDs from older serialized graphs.
        """
        if source not in self.nodes:
            raise ValueError(f"Cannot add edge from unknown source node '{source}'")
        if target not in self.nodes:
            raise ValueError(f"Cannot add edge to unknown target node '{target}'")

        if any(
            edge.source == source
            and edge.target == target
            and edge.condition == condition
            for edge in self.edges.values()
        ):
            raise ValueError(f"Cannot add duplicate edge '{source}' -> '{target}'")

        preferred_key = f"E_{source}->{target}" + ("" if condition else ":false")
        edge_key = preferred_key
        suffix = 1
        while edge_key in self.edges:
            edge_key = f"{preferred_key}:{suffix}"
            suffix += 1
        self.edges[edge_key] = Edge(source=source, target=target, condition=condition)
        return self


def load_srg(data: Any) -> SRG:
    """Validate graph data, a mapping or JSON text, into an ``SRG``.

    Raises ``SRGValidationError`` for invalid fields or structure.
    """
    try:
        if isinstance(data, str | bytes):
            return SRG.model_validate_json(data)
        return SRG.model_validate(data)
    except ValidationError as error:
        structural = [
            str(cause)
            for item in error.errors()
            if isinstance(cause := item.get("ctx", {}).get("error"), SRGValidationError)
        ]
        raise SRGValidationError(structural[0] if structural else str(error)) from error
