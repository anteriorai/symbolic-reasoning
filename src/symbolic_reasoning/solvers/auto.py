"""Auto mode SRG solver with automatic oracle invocation."""

import inspect

from symbolic_reasoning.models import SRG, Coverage, SRGExecution
from symbolic_reasoning.solvers.protocols import AsyncOracle, Oracle
from symbolic_reasoning.solvers.solver import apply_answers, next_request


async def asolve(
    start: SRG | SRGExecution,
    oracle: AsyncOracle | Oracle,
    *,
    coverage: Coverage = Coverage.MINIMAL,
) -> SRGExecution:
    """
    Async solver that automatically invokes the oracle to completion.

    This is the auto mode - you provide an oracle function and the solver
    handles all the invocation automatically. The oracle can be either sync
    or async.

    Args:
        start: The SRG to solve, or an execution to continue from.
        oracle: Oracle function (sync or async) that answers predicates. Bind any
            other arguments it needs with a closure or ``functools.partial``.
        coverage: How much of each aggregator to answer (see ``Coverage``)

    Returns:
        SRGExecution with the answers needed for the selected coverage

    Raises:
        InvalidAnswerError: If the oracle returns an answer that is invalid or
            for a predicate not in the SRG
        ValueError: If a round answers none of the predicates it was asked

    Example:
        # With async oracle
        async def my_oracle(request):
            return {r.predicate.id: Answer(is_met=True, reasoning="...")
                    for r in request.predicate_requests}

        execution = await asolve(srg, my_oracle)

        # With sync oracle
        def my_sync_oracle(request):
            return {r.predicate.id: Answer(is_met=False, reasoning="...")
                    for r in request.predicate_requests}

        execution = await asolve(srg, my_sync_oracle)
    """
    execution = start if isinstance(start, SRGExecution) else SRGExecution(srg=start)

    request = next_request(execution, coverage)

    while request is not None:
        # Inspect the result: async callable objects and sync wrappers returning
        # awaitables also satisfy AsyncOracle, without being coroutine functions.
        response = oracle(request)
        answers = await response if inspect.isawaitable(response) else response

        requested = {r.predicate.id for r in request.predicate_requests}
        if not requested & set(answers):
            raise ValueError(
                "Oracle answered none of the requested predicates "
                f"{sorted(requested)}, so the solve cannot advance"
            )
        execution = apply_answers(execution, answers)
        request = next_request(execution, coverage)

    return execution
