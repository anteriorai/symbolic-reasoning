"""
Solvers for Symbolic Reasoning Graphs

Provides two solving patterns:
1. Auto mode: asolve() - automatic oracle invocation
2. Manual mode: next_request() + apply_answers() - step-by-step user control
"""

from symbolic_reasoning.solvers.auto import asolve
from symbolic_reasoning.solvers.protocols import AsyncOracle, Oracle
from symbolic_reasoning.solvers.requests import OracleRequest, PredicateRequest
from symbolic_reasoning.solvers.solver import apply_answers, next_request

__all__ = [
    "AsyncOracle",
    "Oracle",
    "OracleRequest",
    "PredicateRequest",
    "apply_answers",
    "asolve",
    "next_request",
]
