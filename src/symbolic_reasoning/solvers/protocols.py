"""Protocol definitions for SRG solvers and oracles."""

from collections.abc import Awaitable, Mapping
from typing import Protocol

from symbolic_reasoning.models import Answer
from symbolic_reasoning.solvers.requests import OracleRequest


class AsyncOracle(Protocol):
    """Protocol for async oracle functions.

    Bind any other arguments the oracle needs with a closure or ``functools.partial``.
    """

    def __call__(
        self,
        request: OracleRequest,
        /,
    ) -> Awaitable[Mapping[str, Answer]]: ...


class Oracle(Protocol):
    """Protocol for synchronous oracle functions.

    Bind any other arguments the oracle needs with a closure or ``functools.partial``.
    """

    def __call__(
        self,
        request: OracleRequest,
        /,
    ) -> Mapping[str, Answer]: ...
