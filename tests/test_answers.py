"""Answers are strict and immutable, and rejected batches never echo their contents."""

import traceback

import pytest
from pydantic import ValidationError

from symbolic_reasoning import (
    Answer,
    InvalidAnswerError,
    SRGBuilder,
    SRGExecution,
    apply_answers,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def execution() -> SRGExecution:
    srg = SRGBuilder()
    srg.add_predicate("Is the applicant an adult?")
    return SRGExecution(srg=srg.build())


@pytest.mark.parametrize("value", ["no", "yes", 0, 1, None])
def test_is_met_must_be_a_bool(value: object) -> None:
    with pytest.raises(ValidationError):
        Answer.model_validate({"is_met": value, "reasoning": "r"})


def test_answers_are_frozen() -> None:
    answer = Answer(is_met=True, reasoning="r")
    with pytest.raises(ValidationError):
        answer.is_met = False  # ty: ignore[invalid-assignment]


def test_unknown_predicate_is_an_invalid_answer(execution: SRGExecution) -> None:
    with pytest.raises(InvalidAnswerError, match="not in the SRG") as caught:
        apply_answers(
            execution, {"ghost": Answer(is_met=True, reasoning="Patient SSN 123")}
        )
    assert isinstance(caught.value, ValueError)
    assert execution.answers == {}


@pytest.mark.parametrize(
    "answers",
    [
        {"ghost": {"is_met": True, "reasoning": "Patient SSN 123"}},
        {"Patient SSN 123": {"is_met": True, "reasoning": "r"}},
        {"P1": {"is_met": "no", "reasoning": "Patient SSN 123"}},
        {"P1": {"reasoning": "Patient SSN 123"}},
        {"P1": {"is_met": True, "reasoning": "r", "evidence": "Patient SSN 123"}},
    ],
)
def test_rejected_answers_are_not_echoed(
    execution: SRGExecution, answers: dict[str, object]
) -> None:
    with pytest.raises(InvalidAnswerError) as caught:
        apply_answers(execution, answers)  # ty: ignore[invalid-argument-type]
    assert "Patient SSN" not in "".join(traceback.format_exception(caught.value))


def test_checkpoints_with_unknown_answers_are_not_echoed(
    execution: SRGExecution,
) -> None:
    checkpoint = execution.model_dump(mode="json")
    checkpoint["answers"] = {"Patient SSN 123": {"is_met": True, "reasoning": "r"}}
    with pytest.raises(ValidationError) as caught:
        SRGExecution.model_validate(checkpoint)
    assert "Patient SSN" not in str(caught.value)


def test_answer_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Answer.model_validate({"is_met": True, "reasoning": "r", "confidence": 0.9})
