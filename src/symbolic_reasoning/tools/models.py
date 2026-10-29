"""Results of the SRG agent tools."""

from pydantic import BaseModel, Field

from symbolic_reasoning import Answer, OracleRequest, Outcome, Predicate


class ExecutionProgress(BaseModel):
    """The next predicate request and, once the decision is resolved, its outcomes."""

    request: OracleRequest | None = Field(
        description="Ready predicates, or null when no questions remain"
    )
    outcomes: list[Outcome] | None = Field(
        description=(
            "Null until the decision is resolved; then the reached outcomes, which "
            "may be none. Outcomes can arrive before the last request."
        )
    )


class StartedExecution(ExecutionProgress):
    """An execution handle and its first predicate request."""

    execution_id: str


class PredicateWithAnswer(BaseModel):
    """A predicate's definition and its saved answer, if any."""

    predicate: Predicate
    answer: Answer | None


class PredicateLookup(BaseModel):
    """Predicates and their saved answers, keyed by ID."""

    predicates: dict[str, PredicateWithAnswer]
