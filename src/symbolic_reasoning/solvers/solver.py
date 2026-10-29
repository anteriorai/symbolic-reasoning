"""Stateless, step-by-step SRG solving for user-controlled oracle invocation.

Usage:

    execution = SRGExecution(srg=srg)
    request = next_request(execution)
    while request is not None:
        answers = my_oracle(request)
        execution = apply_answers(execution, answers)
        request = next_request(execution)
"""

from collections.abc import Mapping

from pydantic import ValidationError

from symbolic_reasoning.errors import InvalidAnswerError, validation_problems
from symbolic_reasoning.models import (
    Answer,
    Coverage,
    SRGExecution,
)
from symbolic_reasoning.solvers.requests import OracleRequest, build_request

__all__ = ["OracleRequest", "apply_answers", "next_request"]


def next_request(
    execution: SRGExecution,
    coverage: Coverage = Coverage.MINIMAL,
    *,
    hydrate_context: bool = True,
) -> OracleRequest | None:
    """
    Derive the next oracle request purely from ``execution``.

    Include every ready predicate across reachable branches, deduplicated by ID.
    Each node contributes its next needed predicate under the selected coverage;
    REACHABLE finishes the node's expression before advancing to its children.

    ``hydrate_context`` lists each contextual predicate's definition and answer
    in the request, for oracles that see nothing else. Callers that already
    hold them, or can look them up in the execution, can leave them out.
    """
    return build_request(execution, coverage, hydrate_context=hydrate_context)


def apply_answers(
    execution: SRGExecution, answers: Mapping[str, Answer]
) -> SRGExecution:
    """Return a validated execution with the supplied answers merged in.

    Preserve the graph and existing answers, replacing answers for IDs present
    in the submission. Partial and empty submissions are accepted. IDs absent
    from the graph or invalid answers raise ``InvalidAnswerError`` and leave
    the execution unchanged. The error names each invalid field and the kind
    of failure, never submitted values, unknown IDs or validator messages.

    Neither the input execution nor the supplied mapping is mutated. This
    function does not request more answers or require forward progress; call
    ``next_request`` to determine what remains.
    """
    if unknown := answers.keys() - execution.srg.predicates.keys():
        raise InvalidAnswerError(
            f"Answers for predicates not in the SRG ({len(unknown)})"
        )
    try:
        return SRGExecution(srg=execution.srg, answers={**execution.answers, **answers})
    except ValidationError as error:
        # Validator messages can quote the rejected value.
        raise InvalidAnswerError(
            f"Invalid answers: {validation_problems(error)}"
        ) from None
