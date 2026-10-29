"""The oracle protocols accept any parameter name, and still check the rest.

Most of this file is type-level assertion. The oracles below are never called:
what is under test is whether ty accepts them, so they earn their keep in the
`ty check` CI job rather than under pytest. ty reports unused ignore comments,
so the negative cases bite in both directions: if a protocol stops rejecting one
of them, its `ty: ignore` becomes unused and the type check fails.
"""

from collections.abc import Awaitable, Sequence
from typing import Any

from symbolic_reasoning import is_resolved, outcomes
from symbolic_reasoning.models import SRG, Answer
from symbolic_reasoning.solvers.auto import asolve
from symbolic_reasoning.solvers.protocols import AsyncOracle, Oracle
from symbolic_reasoning.solvers.requests import OracleRequest

# --- accepted: the parameter is positional, so its name is the caller's


async def renamed_async(batch: OracleRequest) -> dict[str, Answer]:
    raise NotImplementedError


def renamed_sync(batch: OracleRequest) -> dict[str, Answer]:
    raise NotImplementedError


async def extra_arguments(
    request: OracleRequest,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Answer]:
    raise NotImplementedError


def returns_awaitable(batch: OracleRequest) -> Awaitable[dict[str, Answer]]:
    raise NotImplementedError


accepts_renamed_async: AsyncOracle = renamed_async
accepts_renamed_sync: Oracle = renamed_sync
accepts_extra_arguments: AsyncOracle = extra_arguments
accepts_awaitable_returning_callable: AsyncOracle = returns_awaitable


# --- rejected: everything other than the names still has to line up


async def wrong_return(batch: OracleRequest) -> Sequence[Answer]:
    raise NotImplementedError


async def wrong_argument(batch: Sequence[str]) -> dict[str, Answer]:
    raise NotImplementedError


async def too_few_parameters() -> dict[str, Answer]:
    raise NotImplementedError


def sync_where_async_expected(batch: OracleRequest) -> dict[str, Answer]:
    raise NotImplementedError


rejects_wrong_return: AsyncOracle = wrong_return  # ty: ignore[invalid-assignment]
rejects_wrong_argument: AsyncOracle = wrong_argument  # ty: ignore[invalid-assignment]
rejects_too_few_parameters: AsyncOracle = too_few_parameters  # ty: ignore[invalid-assignment]
rejects_sync_oracle: AsyncOracle = sync_where_async_expected  # ty: ignore[invalid-assignment]


async def test_asolve_accepts_an_oracle_with_its_own_parameter_names(
    simple_srg: SRG,
) -> None:
    """The names above are a type-level concern; confirm the call itself works."""

    async def oracle(batch: OracleRequest) -> dict[str, Answer]:
        return {
            r.predicate.id: Answer(is_met=True, reasoning="met")
            for r in batch.predicate_requests
        }

    execution = await asolve(simple_srg, oracle)

    assert is_resolved(execution)
    assert [outcome.description for outcome in outcomes(execution)] == ["Success"]
