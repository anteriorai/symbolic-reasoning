"""Oracle request schemas and structural, branch-specific context reconstruction."""

from pydantic import BaseModel, Field

from symbolic_reasoning.models import (
    Answer,
    Coverage,
    Predicate,
    SRGExecution,
    TraceStep,
)
from symbolic_reasoning.models.srg_execution import (
    _ready_predicates_with_contexts,
)


class PredicateRequest(BaseModel):
    """One global fact with known answers merged across its applicable paths."""

    predicate: Predicate
    contextual_predicates: list[TraceStep]


class OracleRequest(BaseModel):
    """One oracle round; answers are keyed by predicate ID.

    Contextual predicates are referenced by ID. When hydrated, each one's
    definition and answer are listed once, in ``predicates`` and ``answers``;
    otherwise both are empty.
    """

    predicate_requests: list[PredicateRequest]
    policy_context: str
    predicates: dict[str, Predicate] = Field(default_factory=dict)
    answers: dict[str, Answer] = Field(default_factory=dict)


def build_request(
    execution: SRGExecution,
    coverage: Coverage = Coverage.MINIMAL,
    *,
    hydrate_context: bool = True,
) -> OracleRequest | None:
    """Build one request per ready predicate, each with its own merged context.

    Contextual answers use the same immutable Answer model as the execution.
    """
    contexts = _ready_predicates_with_contexts(execution, coverage)
    if not contexts:
        return None
    contextual = (
        dict.fromkeys(p_id for ids in contexts.values() for p_id in ids)
        if hydrate_context
        else {}
    )
    return OracleRequest(
        predicate_requests=[
            PredicateRequest(
                predicate=execution.srg.predicates[predicate_id],
                contextual_predicates=[
                    TraceStep(predicate_id=p_id, is_met=execution.answers[p_id].is_met)
                    for p_id in contextual_ids
                ],
            )
            for predicate_id, contextual_ids in contexts.items()
        ],
        policy_context=execution.srg.policy_context or "",
        predicates={p_id: execution.srg.predicates[p_id] for p_id in contextual},
        answers={p_id: execution.answers[p_id] for p_id in contextual},
    )
