"""Record answer batches and reconstruct execution snapshots, with optional JSON I/O."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticSerializationError

from symbolic_reasoning.models import SRG, Answer, SRGExecution


def _copy_answers(answers: Mapping[str, Answer]) -> dict[str, Answer]:
    _require_saveable(answers)
    return dict(answers)


def _validate_predicates(srg: SRG, answers: Mapping[str, Answer]) -> None:
    if unknown := answers.keys() - srg.predicates.keys():
        raise ValueError(f"Answers for predicates not in the SRG ({len(unknown)})")


def _require_saveable(answers: Mapping[str, Answer]) -> None:
    """Reject an answer the history file cannot hold, such as a reply cut mid-emoji."""
    for predicate_id, answer in answers.items():
        try:
            answer.model_dump_json()
        except PydanticSerializationError:
            raise ValueError(
                f"Answer for '{predicate_id}' cannot be saved as JSON"
                " (for example text that is not valid Unicode)"
            ) from None


class ExecutionHistory(BaseModel):
    """Store a graph, initial answers, and ordered answer batches.

    Answer IDs must reference predicates in the graph. Fields cannot be
    reassigned, but nested containers remain mutable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    srg: SRG
    initial_answers: dict[str, Answer] = Field(default_factory=dict)
    batches: tuple[dict[str, Answer], ...] = ()

    @classmethod
    def from_execution(cls, execution: SRGExecution) -> ExecutionHistory:
        """Copy an execution's graph and answers into a history with no batches."""
        return cls(
            srg=SRG.model_validate(execution.srg.model_dump()),
            initial_answers=_copy_answers(execution.answers),
        ).model_copy(deep=True)

    @model_validator(mode="after")
    def _validate_answers(self) -> ExecutionHistory:
        for answers in (self.initial_answers, *self.batches):
            _validate_predicates(self.srg, answers)
            _require_saveable(answers)
        return self


def snapshot(history: ExecutionHistory, step: int = -1) -> SRGExecution:
    """Return one execution state; zero is the start and -1 the latest recorded.

    Step N includes the first N batches. Negative indices count from the end;
    invalid indices raise IndexError. Later batches replace earlier answers
    for the same predicate. The result is a deep copy and may be unresolved.
    """
    count = len(history.batches) + 1
    if step < 0:
        step += count
    if not 0 <= step < count:
        raise IndexError("History step out of range")
    answers: dict[str, Answer] = dict(history.initial_answers)
    for batch in history.batches[:step]:
        answers.update(batch)
    return SRGExecution(srg=history.srg, answers=dict(answers)).model_copy(deep=True)


def save_history_file(history: ExecutionHistory, file_path: str | Path) -> None:
    """Write a history as local JSON, replacing an existing file at this path."""
    Path(file_path).write_text(history.model_dump_json(indent=2), encoding="utf-8")


def load_history_file(file_path: str | Path) -> ExecutionHistory:
    """Read and validate a history from a local JSON file."""
    return ExecutionHistory.model_validate_json(
        Path(file_path).read_text(encoding="utf-8")
    )


class ExecutionRecorder:
    """Copy an execution history and append answer batches in memory."""

    def __init__(
        self, history: ExecutionHistory, *, file_path: str | Path | None = None
    ) -> None:
        if not isinstance(history, ExecutionHistory):
            raise TypeError("history must be an ExecutionHistory")
        owned = history.model_copy(deep=True)
        self._srg = owned.srg
        self._initial_answers = owned.initial_answers
        self._batches: list[dict[str, Answer]] = list(owned.batches)
        self._file_path = file_path

    def export_history(self) -> ExecutionHistory:
        """Return a deep copy of the graph, initial answers, and collected batches."""
        return ExecutionHistory(
            srg=self._srg,
            initial_answers=self._initial_answers,
            batches=tuple(self._batches),
        ).model_copy(deep=True)

    def record(self, answers: Mapping[str, Answer]) -> None:
        """Append a copy of a batch; reject IDs absent from the graph's predicates.

        With a file path, the history is saved after each batch, so a process
        stopped from outside keeps every answer it recorded.
        """
        _validate_predicates(self._srg, answers)
        batch = _copy_answers(answers)
        if self._file_path is not None:
            # Save first: a batch that could not be saved is not recorded either.
            history = self.export_history()
            save_history_file(
                history.model_copy(update={"batches": (*history.batches, batch)}),
                self._file_path,
            )
        self._batches.append(batch)


@contextmanager
def record_execution(
    history: ExecutionHistory, *, file_path: str | Path | None = None
) -> Generator[ExecutionRecorder]:
    """Append to a copy of a history, optionally saving it as JSON.

    Existing batches are preserved. Each record() call appends one batch.
    When file_path is supplied, the complete history is saved after every
    batch and again on normal or exceptional exit; parent directories must
    exist. The input is unchanged.
    """
    recorder = ExecutionRecorder(history, file_path=file_path)
    try:
        yield recorder
    finally:
        if file_path is not None:
            save_history_file(recorder.export_history(), file_path)
