"""The agent workflow over SRG executions, independent of any agent framework.

Each tool takes the host's execution store first, then the arguments the agent
supplies. The host binds its store for each call, as ``ToolSpec.bind`` does; the
store is never part of the agent's schema.
"""

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import partial, wraps
from typing import Annotated, Protocol, get_type_hints

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    validate_call,
)
from pydantic.json_schema import JsonSchemaValue

import symbolic_reasoning as core
from symbolic_reasoning import (
    Answer,
    Coverage,
    ExecutionNotResolvedError,
    InvalidAnswerError,
    ReasoningTrace,
    SRGExecution,
)
from symbolic_reasoning.errors import validation_problems

from .models import (
    ExecutionProgress,
    PredicateLookup,
    PredicateWithAnswer,
)

ExecutionId = Annotated[str, Field(description="ID of the execution")]
PredicateIds = Annotated[
    list[str], Field(description="IDs of the predicates to look up")
]
AnswersById = Annotated[
    dict[str, Answer], Field(description="Answers keyed by predicate ID")
]

CoverageArgument = Annotated[
    Coverage,
    Field(
        description=(
            "minimal asks only what deciding the outcome needs, stopping at the first "
            "failed requirement; reachable also finishes every requirement on the "
            "branches the case reaches, so the record shows each unmet one. "
            "The execution keeps this coverage."
        )
    ),
]

INSTRUCTIONS = (
    "Each tool acts on one execution of an SRG, named by its execution ID. "
    "Starting an execution returns its ID and first request. "
    "Answer each predicate's question using its context, the policy_context and contextual_predicates, "
    "which list the answers already given on the way to it. A request's predicates and answers are empty; "
    "call get_predicates for questions and answers you have already seen. "
    "Answer every requested predicate, keyed by predicate ID; unanswered ones are asked again. "
    "You may split a request across several submissions. Resubmitting a predicate replaces its answer, "
    "and changing an answer can change the outcome or reopen a resolved decision. "
    "Keep answering until request is null. outcomes is null until the decision is resolved, then lists "
    "the reached outcomes; they can arrive before the last request. "
    "Reaching no outcome is not an approval or a denial. "
    "After an interrupted submission, resubmit the batch or call get_predicate_requests with the same ID. "
    "get_reasoning_trace explains a resolved decision with paths that reference predicates by ID; "
    "call get_predicates for their questions and saved answers."
)


class ToolError(Exception):
    """A tool call the agent can correct, with a message addressed to the agent."""


class StoredExecution(BaseModel):
    """An execution and the coverage it is solved to, as the host keeps them."""

    model_config = ConfigDict(frozen=True)

    execution: SRGExecution
    coverage: Coverage


class ExecutionStore(Protocol):
    """The host's executions, named by the IDs it gives the agent.

    Starting executions and choosing their IDs and coverage are the host's.
    """

    async def load(self, execution_id: str) -> StoredExecution:
        """Return the execution; raise `ToolError` when the ID is unknown."""
        ...

    async def save_answers(
        self, execution_id: str, answers: Mapping[str, Answer]
    ) -> StoredExecution:
        """Save validated answers, replacing earlier answers to the same predicates.

        Return the execution as committed, with any answers other writers saved first.
        """
        ...


class ToolHints(BaseModel):
    """How a tool affects its execution, for hosts that surface it to the agent."""

    read_only: bool
    destructive: bool
    idempotent: bool


READ_ONLY = ToolHints(read_only=True, destructive=False, idempotent=True)
# Resubmitting a predicate replaces its answer; the same batch twice changes nothing.
OVERWRITING = ToolHints(read_only=False, destructive=True, idempotent=True)


def progress(stored: StoredExecution) -> ExecutionProgress:
    """The execution's next request and, once its decision is resolved, its outcomes."""
    execution = stored.execution
    return ExecutionProgress(
        request=core.next_request(execution, stored.coverage, hydrate_context=False),
        outcomes=core.outcomes(execution) if core.is_resolved(execution) else None,
    )


async def get_predicate_requests(
    store: ExecutionStore, execution_id: ExecutionId
) -> ExecutionProgress:
    """Get ready predicates with their contexts and, once resolved, the outcomes."""
    return progress(await store.load(execution_id))


async def submit_answers(
    store: ExecutionStore, execution_id: ExecutionId, answers: AnswersById
) -> ExecutionProgress:
    """Submit answers and return the next request and, once resolved, the outcomes.

    Answers for any predicates in the graph are saved; requested predicates
    left unanswered come back next call. Resubmitting a predicate replaces
    its saved answer, which can change the outcome or reopen a resolved
    decision.
    """
    try:
        core.apply_answers((await store.load(execution_id)).execution, answers)
    except InvalidAnswerError as exc:
        raise ToolError(str(exc)) from exc
    return progress(await store.save_answers(execution_id, answers))


async def get_reasoning_trace(
    store: ExecutionStore, execution_id: ExecutionId
) -> ReasoningTrace:
    """Get outcome paths and all explored paths, including dead ends. Requires a resolved decision.

    This is the graph's logical justification, not a chronological tool-call log.
    """
    try:
        return core.reasoning_trace((await store.load(execution_id)).execution)
    except ExecutionNotResolvedError:
        raise ToolError(
            "Decision is not resolved. Call get_predicate_requests to see the remaining questions."
        ) from None


async def get_predicates(
    store: ExecutionStore, execution_id: ExecutionId, predicate_ids: PredicateIds
) -> PredicateLookup:
    """Get predicate definitions and their saved answers, or null when unanswered, by ID."""
    execution = (await store.load(execution_id)).execution
    predicates = execution.srg.predicates
    if unknown := sorted(set(predicate_ids) - set(predicates)):
        raise ToolError(f"Predicates not in the SRG: {unknown}")
    return PredicateLookup(
        predicates={
            i: PredicateWithAnswer(
                predicate=predicates[i], answer=execution.answers.get(i)
            )
            for i in predicate_ids
        }
    )


@dataclass(frozen=True)
class ToolSpec:
    """One tool to register with an agent framework."""

    name: str
    fn: Callable[..., Awaitable[BaseModel]]
    hints: ToolHints

    def bind(self, store: ExecutionStore) -> Callable[..., Awaitable[BaseModel]]:
        """The tool as the agent calls it, over the host's store.

        It validates the agent's arguments, so it can be called with them as
        decoded JSON, and raises `ToolError` for arguments that fail.
        """
        fn = self.fn

        # Synchronous, so its arguments are validated when it is called rather
        # than when the coroutine runs, keeping errors from the tool body apart.
        @wraps(fn)
        def start(*args: object, **kwargs: object) -> Awaitable[BaseModel]:
            return fn(*args, **kwargs)

        bound = partial(fn, store)
        validated = validate_call(partial(start, store))

        @wraps(bound)
        async def tool(**arguments: object) -> BaseModel:
            try:
                pending = validated(**arguments)
            except ValidationError as error:
                raise ToolError(
                    f"Invalid arguments: {validation_problems(error)}"
                ) from None
            return await pending

        return tool

    @property
    def description(self) -> str:
        return inspect.getdoc(self.fn) or ""

    @property
    def input_schema(self) -> JsonSchemaValue:
        # The schema covers only what follows the bound store, so no store is needed.
        return TypeAdapter(partial(self.fn, None)).json_schema()

    @property
    def output_schema(self) -> JsonSchemaValue:
        return TypeAdapter(get_type_hints(self.fn)["return"]).json_schema()


TOOLS = [
    ToolSpec(fn.__name__, fn, hints)
    for fn, hints in [
        (get_predicate_requests, READ_ONLY),
        (submit_answers, OVERWRITING),
        (get_reasoning_trace, READ_ONLY),
        (get_predicates, READ_ONLY),
    ]
]
