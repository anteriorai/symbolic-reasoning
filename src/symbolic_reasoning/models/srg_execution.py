from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from enum import Enum
from graphlib import TopologicalSorter
from typing import final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)

from symbolic_reasoning.errors import ExecutionNotResolvedError
from symbolic_reasoning.gen.py.srg import (
    Aggregator,
    Node,
    Outcome,
    Predicate,
    Root,
)

from .aggregator_logic import evaluate_strategy
from .srg import ROOT_ID, SRG


class Coverage(str, Enum):
    """How much of the graph a solve answers."""

    MINIMAL = "minimal"
    """Only what deciding the outcome requires, stopping at each short-circuit."""

    REACHABLE = "reachable"
    """Every predicate the answers lead to, verdict-changing or not.

    Never one behind a branch the answers do not take, so it cannot reach an
    outcome a ``MINIMAL`` solve would not.
    """

    # TODO: COMPLETE - every predicate in the graph, including those behind
    # branches the answers never take.


@final
class Answer(BaseModel):
    """An immutable verdict and reasoning; application metadata belongs in host records."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    is_met: StrictBool = Field(description="Whether the predicate's question holds")
    reasoning: str = Field(description="Why it holds or not, from the evidence")


class TraceStep(BaseModel):
    """An answered predicate, by ID, and its verdict."""

    predicate_id: str
    is_met: StrictBool


class TracePath(BaseModel):
    """A path through the reasoning graph, represented as predicate evaluation steps."""

    steps: list[TraceStep]


class OutcomePath(TracePath):
    """A path that reached an outcome."""

    outcome_id: str


class ReasoningTrace(BaseModel):
    """Canonical interpretation artifact for a completed SRGExecution.

    Paths reference predicates and outcomes by ID; look them up in the
    execution's ``srg`` and ``answers``.
    """

    outcome_paths: list[OutcomePath] = Field(default_factory=list)
    all_paths: list[TracePath] = Field(default_factory=list)


class SRGExecution(BaseModel):
    """
    Execution state: a graph and the answers known so far.

    Fields cannot be reassigned, and ``apply_answers`` returns a new execution.
    Answers contain only ``is_met`` and ``reasoning``. Serialize with
    ``model_dump_json()`` and restore with ``SRGExecution.model_validate_json()``.

    Interpret one with the functions in this module, such as
    ``outcomes(execution)`` and ``reasoning_trace(execution)``.
    """

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    srg: SRG
    answers: Mapping[str, Answer] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _answers_are_known_predicates(self) -> SRGExecution:
        if unknown := self.answers.keys() - self.srg.predicates.keys():
            raise ValueError(f"Answers for predicates not in the SRG ({len(unknown)})")
        return self


def _item(
    srg: SRG, item_id: str
) -> Predicate | Aggregator | Outcome | Node | Root | None:
    """The symbol or node with this ID; Root is its own symbol."""
    if item_id == ROOT_ID:
        return Root()
    return (
        srg.predicates.get(item_id)
        or srg.aggregators.get(item_id)
        or srg.outcomes.get(item_id)
        or srg.nodes.get(item_id)
    )


def _targets(srg: SRG, node_id: str) -> list[tuple[str, bool]]:
    """A node's outgoing edges as (target, condition), sorted by target."""
    return sorted(
        (
            (edge.target, edge.condition)
            for edge in srg.edges.values()
            if edge.source == node_id
        ),
        key=lambda target: target[0],
    )


def _predicates_under(srg: SRG, item_id: str) -> list[Predicate]:
    """Every distinct predicate under an item, depth first in argument order."""
    predicates: list[Predicate] = []
    seen: set[str] = set()

    def collect(item_id: str) -> None:
        if item_id in seen:
            return
        seen.add(item_id)
        item = _item(srg, item_id)
        if isinstance(item, Predicate):
            predicates.append(item)
        elif isinstance(item, Aggregator):
            for argument_id in item.argument_ids:
                collect(argument_id)
        elif isinstance(item, Node):
            collect(item.item_id)

    collect(item_id)
    return predicates


def _to_trace_steps(pairs: Sequence[tuple[Predicate, Answer]]) -> list[TraceStep]:
    return [
        TraceStep(predicate_id=predicate.id, is_met=answer.is_met)
        for predicate, answer in pairs
    ]


def reasoning_trace(execution: SRGExecution) -> ReasoningTrace:
    """
    Return the canonical interpretation artifact for this execution.

    - outcome_paths: reached outcomes with the predicate evaluations that led to them
    - all_paths: every path the solver explored (both complete and incomplete)
    """
    return ReasoningTrace(
        outcome_paths=[
            OutcomePath(outcome_id=outcome.id, steps=_to_trace_steps(pairs))
            for outcome, pairs in _outcome_paths(execution)
        ],
        all_paths=[
            TracePath(steps=_to_trace_steps(pairs))
            for pairs in _all_distinct_paths(execution)
        ],
    )


def outcomes(execution: SRGExecution) -> list[Outcome]:
    """Return distinct outcomes reached by this execution."""
    unique_outcomes: dict[str, Outcome] = {}
    for outcome, _ in _outcome_paths(execution):
        unique_outcomes[outcome.id] = outcome
    return list(unique_outcomes.values())


def evaluate_symbol(execution: SRGExecution, symbol_id: str) -> bool | None:
    return _evaluate_symbol(execution, symbol_id, {})


def _evaluate_symbol(
    execution: SRGExecution, symbol_id: str, verdicts: dict[str, bool | None]
) -> bool | None:
    """
    Evaluate a symbol, reusing verdicts already reached in this pass.

    ``verdicts`` is a parameter, not state: it is only sound while ``answers``
    cannot change.
    """
    if symbol_id in verdicts:
        return verdicts[symbol_id]

    symbol = _item(execution.srg, symbol_id)
    verdict: bool | None

    if isinstance(symbol, Root):
        verdict = True
    elif isinstance(symbol, Predicate):
        answer = execution.answers.get(symbol.id)
        verdict = answer.is_met if answer is not None else None
    elif isinstance(symbol, Aggregator):
        evaluations = [
            _evaluate_symbol(execution, arg, verdicts) for arg in symbol.argument_ids
        ]
        effective: list[bool | None] = [
            (e if symbol.truth_value else not e) if e is not None else None
            for e in evaluations
        ]
        verdict = evaluate_strategy(symbol.strategy, effective)
    elif isinstance(symbol, Outcome):
        # Terminal: no edge condition matches None, so a walk stops here.
        verdict = None
    elif isinstance(symbol, Node):
        verdict = _evaluate_symbol(execution, symbol.item_id, verdicts)
    else:
        raise TypeError(f"Unknown symbol type: {type(symbol)}")

    verdicts[symbol_id] = verdict
    return verdict


def _frontier(execution: SRGExecution) -> list[Predicate]:
    """
    Every predicate still needed to decide the graph, in the order asked.

    Breadth first, like the solver. Reachability-bounded: a node is only
    entered along edges whose condition matches its verdict, so predicates
    behind a branch the graph does not take are never outstanding. Empty as
    soon as the graph is decided - not when every predicate has an answer,
    which is what lets short-circuiting stand.
    """
    # Deciding the graph never depends on coverage; see is_resolved.
    return [
        execution.srg.predicates[p_id]
        for p_id in _ready_predicates_with_contexts(execution, Coverage.MINIMAL)
    ]


def _ready_predicates_with_contexts(
    execution: SRGExecution, coverage: Coverage
) -> dict[str, tuple[str, ...]]:
    """Map each predicate ready to be answered to the known facts that apply to it.

    At ``MINIMAL`` the keys are the frontier; wider coverages add predicates
    the outcome does not depend on.

    Discover reachable nodes once, retaining incoming edges at convergence.
    Propagate context in topological order so longer paths contribute before
    descendants are processed, then emit the keys in BFS order. This merges
    facts without enumerating paths.
    """
    # Accept the enum or its value; anything else is an error, not REACHABLE.
    coverage = Coverage(coverage)
    parents: dict[str, list[str]] = {ROOT_ID: []}
    pending: dict[str, list[Predicate]] = {}
    verdicts: dict[str, bool | None] = {}
    queue = deque([ROOT_ID])

    while queue:
        node_id = queue.popleft()
        needed = _next_needed_predicates(execution, node_id, coverage)
        if needed:
            pending[node_id] = needed
            continue
        is_met = _evaluate_symbol(execution, node_id, verdicts)
        for target_id, condition in _targets(execution.srg, node_id):
            if condition == is_met:
                if target_id not in parents:
                    parents[target_id] = []
                    queue.append(target_id)
                parents[target_id].append(node_id)

    contexts: dict[str, dict[str, None]] = {}
    for node_id in TopologicalSorter(parents).static_order():
        context: dict[str, None] = {}
        for parent_id in parents[node_id]:
            context.update(contexts[parent_id])
        context.update((p.id, None) for p in _answered_predicates(execution, node_id))
        contexts[node_id] = context

    ready: dict[str, dict[str, None]] = {}
    for node_id, predicates in pending.items():
        for predicate in predicates:
            ready.setdefault(predicate.id, {}).update(contexts[node_id])
    return {p_id: tuple(context) for p_id, context in ready.items()}


def is_resolved(execution: SRGExecution) -> bool:
    """Whether the graph is decided and needs no further answers.

    Judged on what deciding requires, never on coverage: answering beyond that
    is gathering, not solving, and must not make an execution uninterpretable.
    A ``MINIMAL`` solve is resolved even though ``REACHABLE`` would ask more.
    """
    return not _frontier(execution)


def _require_resolved(execution: SRGExecution) -> None:
    pending = _frontier(execution)
    if pending:
        raise ExecutionNotResolvedError(
            f"Execution is not resolved: {len(pending)} predicate(s) still need "
            f"answers (first: {pending[0].id}). Finish solving before "
            f"interpreting it; next_request(execution) returns what to ask next."
        )


def _next_needed_predicates(
    execution: SRGExecution, item_id: str, coverage: Coverage = Coverage.MINIMAL
) -> list[Predicate]:
    """
    The predicate(s) outstanding for an item under this coverage.

    Arguments are walked in order and one predicate is returned at a time, so
    a solve is equally sequential under any coverage. ``MINIMAL`` stops as soon
    as the verdict is determined; ``REACHABLE`` continues until the subtree has
    no unanswered predicate left.

    A node id answers for the item it wraps.
    """
    # Accept the enum or its value; anything else is an error, not REACHABLE.
    coverage = Coverage(coverage)
    item = _item(execution.srg, item_id)

    if isinstance(item, Predicate):
        return [] if item.id in execution.answers else [item]

    elif isinstance(item, Node):
        return _next_needed_predicates(execution, item.item_id, coverage)

    elif isinstance(item, Aggregator):
        stop_at_verdict = coverage == Coverage.MINIMAL
        if stop_at_verdict and evaluate_symbol(execution, item.id) is not None:
            return []
        # The first argument with anything left. An argument needing nothing
        # returns nothing, so a settled subtree is skipped without a second
        # verdict check - and under REACHABLE it is entered rather than
        # skipped, which is what keeps nested short-circuits from stranding.
        for arg_id in item.argument_ids:
            outstanding = _next_needed_predicates(execution, arg_id, coverage)
            if outstanding:
                return outstanding
        return []

    else:  # Root and Outcome hold no predicates
        return []


def _outcome_paths(
    execution: SRGExecution, start_node_id: str = ROOT_ID
) -> list[tuple[Outcome, list[tuple[Predicate, Answer]]]]:
    """
    Get all paths from the start node to the outcomes.
    Returns a list of tuples containing (Outcome, list of (Predicate, Answer) tuples)
    representing the predicates and their answers along each path to an outcome.

    Args:
        start_node_id: Node ID to start traversal from (default: "Root")

    Raises
    ------
    ExecutionNotResolvedError
        If the execution still needs answers to finish solving.
    """
    _require_resolved(execution)

    paths: list[tuple[Outcome, list[tuple[Predicate, Answer]]]] = []
    stack: list[tuple[str, list[tuple[Predicate, Answer]]]] = [(start_node_id, [])]

    while stack:
        node_id, prev_predicates = stack.pop()
        node = execution.srg.nodes[node_id]
        node_item = _item(execution.srg, node.item_id)

        # If we've reached an outcome, add the path
        if isinstance(node_item, Outcome):
            paths.append((node_item, prev_predicates))
            continue

        # Evaluate the node to determine which paths to follow
        is_met = evaluate_symbol(execution, node.item_id)
        if is_met is None:
            continue

        current_predicates = _extend_path(execution, prev_predicates, node.item_id)

        # Get all targets and their conditions
        for target_id, condition in _targets(execution.srg, node_id):
            # Only follow paths where the condition matches the evaluation
            if condition == is_met:
                stack.append((target_id, current_predicates))

    return paths


def _all_distinct_paths(
    execution: SRGExecution, start_node_id: str = ROOT_ID
) -> list[list[tuple[Predicate, Answer]]]:
    """
    Get all distinct paths from the start node, regardless of whether they end in outcomes.
    Returns a list of lists, where each inner list contains (Predicate, Answer) tuples
    representing the predicates and their answers along each distinct path. Paths are considered
    terminal when they either:
    1. Reach a leaf node (no outgoing edges)
    2. Cannot continue due to condition mismatches
    3. Reach a node where evaluation returns None

    Args:
        start_node_id: Node ID to start traversal from (default: "Root")

    Raises
    ------
    ExecutionNotResolvedError
        If the execution still needs answers to finish solving.
    """
    _require_resolved(execution)

    paths: list[list[tuple[Predicate, Answer]]] = []
    stack: list[tuple[str, list[tuple[Predicate, Answer]]]] = [(start_node_id, [])]

    while stack:
        node_id, prev_predicates = stack.pop()
        node = execution.srg.nodes[node_id]

        current_predicates = _extend_path(execution, prev_predicates, node.item_id)

        # Get all targets and their conditions
        targets = _targets(execution.srg, node_id)

        if not targets:
            # This is a leaf node - add the path
            paths.append(current_predicates)
            continue

        # Try to continue traversal to targets
        # Evaluate the node to determine which paths to follow
        is_met = evaluate_symbol(execution, node.item_id)

        if is_met is None:
            paths.append(current_predicates)
            continue

        valid_paths_found = False
        for target_id, condition in targets:
            # Only follow paths where the condition matches the evaluation
            if condition == is_met:
                stack.append((target_id, current_predicates))
                valid_paths_found = True

        # If no valid paths forward, this is a terminal node for this execution
        if not valid_paths_found:
            paths.append(current_predicates)

    return paths


def _answered_predicates(execution: SRGExecution, item_id: str) -> list[Predicate]:
    """
    Every answered predicate in this item's subtree, in argument order.

    Reports what was answered, not what mattered - which predicates to answer
    is the solver's concern. Carrying no strategy or count logic, it cannot
    drift from :func:`evaluate_strategy`. Unanswered predicates are absent.
    """
    return [
        predicate
        for predicate in _predicates_under(execution.srg, item_id)
        if predicate.id in execution.answers
    ]


def _extend_path(
    execution: SRGExecution,
    prev_predicates: list[tuple[Predicate, Answer]],
    item_id: str,
) -> list[tuple[Predicate, Answer]]:
    """Append this item's answers to a path, without repeating earlier ones."""
    seen = {predicate.id for predicate, _ in prev_predicates}
    return prev_predicates + [
        (predicate, execution.answers[predicate.id])
        for predicate in _answered_predicates(execution, item_id)
        if predicate.id not in seen
    ]
