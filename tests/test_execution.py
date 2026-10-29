"""Executions are read-only and can resume a solve."""

import pytest
from pydantic import ValidationError

from symbolic_reasoning import (
    SRG,
    Answer,
    OracleRequest,
    SRGExecution,
    apply_answers,
    asolve,
    compile_srg_string,
    outcomes,
)

SOURCE = """
predicate adult: "Is the applicant an adult?"
predicate employed: "Is the applicant employed?"
outcome approved: "Approved"
path approve: all(adult, employed) => approved
"""


@pytest.fixture
def srg() -> SRG:
    return compile_srg_string(SOURCE)


def test_execution_is_frozen(srg: SRG) -> None:
    execution = SRGExecution(srg=srg)
    with pytest.raises(ValidationError):
        execution.answers = {}  # ty: ignore[invalid-assignment]


async def test_asolve_continues_a_partial_execution(srg: SRG) -> None:
    asked: list[str] = []

    async def oracle(request: OracleRequest) -> dict:
        asked.extend(r.predicate.id for r in request.predicate_requests)
        return {
            r.predicate.id: Answer(is_met=True, reasoning="r")
            for r in request.predicate_requests
        }

    partial = apply_answers(
        SRGExecution(srg=srg), {"adult": Answer(is_met=True, reasoning="r")}
    )
    execution = await asolve(partial, oracle)

    assert asked == ["employed"]
    assert [o.id for o in outcomes(execution)] == ["approved"]
