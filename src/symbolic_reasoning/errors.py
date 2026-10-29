"""Errors raised by the symbolic_reasoning runtime."""

from pydantic import ValidationError


class InvalidAnswerError(ValueError):
    """An answer batch was rejected; the execution is unchanged."""


def validation_problems(error: ValidationError) -> str:
    """Where and how validation failed, without the rejected values."""
    return "; ".join(
        f"{'.'.join(map(str, item['loc']))}: {item['type']}"
        for item in error.errors(include_input=False, include_context=False)
    )


class ExecutionNotResolvedError(RuntimeError):
    """Raised when an execution is interpreted before it has finished solving."""
