"""Record applied answer batches and reconstruct independent execution snapshots."""

import json
from contextlib import nullcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from symbolic_reasoning import (
    Answer,
    Coverage,
    ExecutionHistory,
    ExecutionNotResolvedError,
    SRGBuilder,
    SRGExecution,
    apply_answers,
    compile_srg_string,
    is_resolved,
    load_history_file,
    next_request,
    outcomes,
    reasoning_trace,
    record_execution,
    save_history_file,
    snapshot,
)
from symbolic_reasoning.models import SRG, evaluate_symbol
from symbolic_reasoning.recording import ExecutionRecorder


def test_snapshot_every_batch_and_final_trace(simple_srg: SRG, tmp_path: Path) -> None:
    execution = SRGExecution(srg=simple_srg)
    recorder = ExecutionRecorder(ExecutionHistory.from_execution(execution))
    states = [execution]
    while request := next_request(execution):
        answers = {
            r.predicate.id: Answer(is_met=True, reasoning="Confirmed")
            for r in request.predicate_requests
        }
        execution = apply_answers(execution, answers)
        recorder.record(answers)
        states.append(execution)

    path = tmp_path / "history.json"
    save_history_file(recorder.export_history(), path)
    loaded = load_history_file(path)
    for index, state in enumerate(states):
        restored = snapshot(loaded, index)
        assert restored.model_dump() == state.model_dump()
        restored_request, original_request = next_request(restored), next_request(state)
        assert (restored_request.model_dump() if restored_request else None) == (
            original_request.model_dump() if original_request else None
        )
    assert reasoning_trace(snapshot(loaded)).model_dump() == (
        reasoning_trace(execution).model_dump()
    )
    with pytest.raises(ExecutionNotResolvedError):
        reasoning_trace(snapshot(loaded, 0))


def test_partial_batches_and_corrections_from_a_mid_run_start(simple_srg: SRG) -> None:
    a, b = simple_srg.predicates
    execution = SRGExecution(
        srg=simple_srg, answers={a: Answer(is_met=True, reasoning="Initial")}
    )
    recorder = ExecutionRecorder(ExecutionHistory.from_execution(execution))
    recorder.record({b: Answer(is_met=True, reasoning="Second")})
    recorder.record({a: Answer(is_met=False, reasoning="Corrected")})
    recording = recorder.export_history()

    assert set(snapshot(recording, 0).answers) == {a}
    assert snapshot(recording, 1).answers[a].is_met
    assert not snapshot(recording).answers[a].is_met
    assert snapshot(recording).answers[a].reasoning == "Corrected"
    assert set(snapshot(recording).answers) == {a, b}
    assert [set(batch) for batch in recording.batches] == [{b}, {a}]


def test_record_and_snapshot_do_not_share_mutable_data(simple_srg: SRG) -> None:
    a = next(iter(simple_srg.predicates))
    execution = SRGExecution(
        srg=simple_srg, answers={a: Answer(is_met=True, reasoning="Yes")}
    )
    recorder = ExecutionRecorder(ExecutionHistory.from_execution(execution))
    original = recorder.export_history()
    original_json = original.model_dump_json()
    batch = {a: Answer(is_met=False, reasoning="Updated")}
    recorder.record(batch)
    updated = recorder.export_history()

    updated.initial_answers.clear()

    assert original.model_dump_json() == original_json
    assert updated.batches[0][a].reasoning == "Updated"
    assert a in updated.srg.predicates


def test_shared_predicate_is_recorded_once_and_applies_to_all_nodes() -> None:
    srg = SRGBuilder()
    predicate_id = srg.add_predicate("Shared question")
    left, right = srg.add_node(predicate_id), srg.add_node(predicate_id)
    srg.add_edge("Root", left)
    srg.add_edge("Root", right)
    execution = SRGExecution(srg=srg.build())
    recorder = ExecutionRecorder(ExecutionHistory.from_execution(execution))
    recorder.record({predicate_id: Answer(is_met=True, reasoning="Shared fact")})
    recording = recorder.export_history()
    restored = snapshot(recording)
    assert evaluate_symbol(restored, left) is True
    assert evaluate_symbol(restored, right) is True
    assert len(recording.batches[0]) == 1


def test_more_answers_can_be_recorded_after_decision_resolves(
    all_strategy_srg: SRG,
) -> None:
    a, b, _ = all_strategy_srg.predicates
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=all_strategy_srg))
    )
    recorder.record({a: Answer(is_met=False, reasoning="No")})
    resolved = snapshot(recorder.export_history())
    assert is_resolved(resolved)
    assert next_request(resolved) is None
    assert next_request(resolved, Coverage.REACHABLE) is not None
    recorder.record({b: Answer(is_met=True, reasoning="Extra fact")})
    recording = recorder.export_history()
    assert outcomes(snapshot(recording)) == outcomes(resolved)
    assert set(snapshot(recording, 1).answers) == {a}
    assert set(snapshot(recording).answers) == {a, b}


def test_batch_is_one_step(simple_srg: SRG) -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=simple_srg))
    )
    batch = {p: Answer(is_met=True, reasoning="Batch") for p in simple_srg.predicates}
    recorder.record(batch)
    recording = recorder.export_history()
    assert len(recording.batches) == 1
    assert not snapshot(recording, 0).answers
    assert len(snapshot(recording, 1).answers) == 2


def test_reject_unknown_predicates_on_record_and_load(simple_srg: SRG) -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=simple_srg))
    )
    with pytest.raises(ValueError, match="not in the SRG"):
        recorder.record({"ghost": Answer(is_met=True, reasoning="No")})
    recording = recorder.export_history()
    assert recording.batches == ()
    for field in ("initial_answers", "batches"):
        payload = recording.model_dump()
        answers = {"ghost": {"is_met": True, "reasoning": "No"}}
        payload[field] = answers if field == "initial_answers" else [answers]
        with pytest.raises(ValueError, match="not in the SRG"):
            ExecutionHistory.model_validate(payload)


def test_empty_run_and_indexing(simple_srg: SRG) -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=simple_srg))
    )
    recording = recorder.export_history()
    assert snapshot(recording).answers == snapshot(recording, 0).answers == {}
    for index in (-2, 1):
        with pytest.raises(IndexError):
            snapshot(recording, index)
    recorder.record({})
    recording = recorder.export_history()
    assert len(recording.batches) == 1
    assert snapshot(recording, -2).answers == {}
    assert snapshot(recording, -1).answers == {}
    with pytest.raises(IndexError):
        snapshot(recording, 2)


def test_context_records_in_memory_and_captures_start(
    simple_srg: SRG,
) -> None:
    a, b = simple_srg.predicates
    execution = SRGExecution(
        srg=simple_srg, answers={a: Answer(is_met=True, reasoning="Existing")}
    )
    with record_execution(ExecutionHistory.from_execution(execution)) as recorder:
        assert set(snapshot(recorder.export_history()).answers) == {a}
        before = recorder.export_history()
        recorder.record({b: Answer(is_met=True, reasoning="New")})
        assert is_resolved(snapshot(recorder.export_history()))
        assert before.batches == ()
    assert len(recorder.export_history().batches) == 1
    assert set(execution.answers) == {a}


def test_context_views_cannot_mutate_the_recording(simple_srg: SRG) -> None:
    with record_execution(
        ExecutionHistory.from_execution(SRGExecution(srg=simple_srg))
    ) as recorder:
        recorder.record({"P1": Answer(is_met=True, reasoning="Fact")})
        view = recorder.export_history()
        view.batches[0].clear()
        assert recorder.export_history().batches[0]["P1"].reasoning == "Fact"
        assert recorder.export_history().srg.predicates


def test_recorder_owns_batches_and_preserves_earlier_exports(simple_srg: SRG) -> None:
    execution = SRGExecution(srg=simple_srg)
    with record_execution(ExecutionHistory.from_execution(execution)) as recorder:
        answer = Answer(is_met=True, reasoning="Original")
        batch: dict[str, Answer] = {"P1": answer}
        recorder.record(batch)
        before = recorder.export_history()
        batch.clear()
        recorder.record({"P1": Answer(is_met=False, reasoning="Correction")})
        after = recorder.export_history()
        assert len(before.batches) == 1
        assert before.batches[0]["P1"].model_dump() == {
            "is_met": True,
            "reasoning": "Original",
        }
        assert after.batches[0] == before.batches[0]
        assert recorder.export_history().batches[0]["P1"].reasoning == "Original"
        assert snapshot(recorder.export_history()).answers["P1"].is_met is False


@pytest.mark.parametrize("as_string", [False, True])
def test_context_saves_same_recording_to_file(
    simple_srg: SRG, tmp_path: Path, as_string: bool
) -> None:
    path = tmp_path / "run.json"
    execution = SRGExecution(srg=simple_srg)
    with record_execution(
        ExecutionHistory.from_execution(execution),
        file_path=str(path) if as_string else path,
    ) as recorder:
        batch = {
            p: Answer(is_met=True, reasoning="Café 🙂") for p in simple_srg.predicates
        }
        execution = apply_answers(execution, batch)
        recorder.record(batch)
    loaded = load_history_file(path)
    assert loaded == recorder.export_history()
    assert snapshot(loaded).model_dump() == execution.model_dump()


@pytest.mark.parametrize("apply_batch", [False, True])
def test_exception_preserves_recording_and_propagates(
    simple_srg: SRG, tmp_path: Path, apply_batch: bool
) -> None:
    path = tmp_path / "interrupted.json"
    error = RuntimeError("Oracle unavailable")
    with (
        pytest.raises(RuntimeError) as raised,
        record_execution(
            ExecutionHistory.from_execution(SRGExecution(srg=simple_srg)),
            file_path=path,
        ) as recorder,
    ):
        if apply_batch:
            recorder.record({"P1": Answer(is_met=True, reasoning="Applied")})
        raise error
    assert raised.value is error
    loaded = load_history_file(path)
    assert len(loaded.batches) == int(apply_batch)
    assert loaded == recorder.export_history()


def test_invalid_batch_does_not_replace_valid_recording(
    simple_srg: SRG, tmp_path: Path
) -> None:
    path = tmp_path / "run.json"
    with (
        pytest.raises(ValueError, match="not in the SRG"),
        record_execution(
            ExecutionHistory.from_execution(SRGExecution(srg=simple_srg)),
            file_path=path,
        ) as recorder,
    ):
        recorder.record({"P1": Answer(is_met=True, reasoning="Valid")})
        recorder.record({"ghost": Answer(is_met=False, reasoning="Invalid")})
    loaded = load_history_file(path)
    assert len(loaded.batches) == 1
    assert set(snapshot(loaded).answers) == {"P1"}


def test_file_write_failure_is_visible(simple_srg: SRG, tmp_path: Path) -> None:
    with (
        pytest.raises(FileNotFoundError),
        record_execution(
            ExecutionHistory.from_execution(SRGExecution(srg=simple_srg)),
            file_path=tmp_path / "missing" / "run.json",
        ),
    ):
        pass


def test_underwriting_snapshot_reconstructs_execution_without_an_oracle(
    underwriting_policy: SRG,
) -> None:
    execution = SRGExecution(srg=underwriting_policy)
    with record_execution(ExecutionHistory.from_execution(execution)) as recorder:
        while request := next_request(execution):
            answers = {
                r.predicate.id: Answer(
                    is_met=r.predicate.id != "has_down_payment", reasoning="Demo fact"
                )
                for r in request.predicate_requests
            }
            execution = apply_answers(execution, answers)
            recorder.record(answers)

    recording = recorder.export_history()
    assert [len(batch) for batch in recording.batches] == [2, 2, 1, 1, 1]
    assert set(recording.batches[-1]) == {"has_reserves"}
    loaded = ExecutionHistory.model_validate_json(recording.model_dump_json())
    final = snapshot(loaded)
    assert [outcome.id for outcome in outcomes(final)] == ["manual_review"]
    assert (
        reasoning_trace(final).model_dump() == reasoning_trace(execution).model_dump()
    )


@pytest.mark.parametrize("interrupted", [False, True])
def test_resume_preserves_saved_batches_and_snapshots(
    underwriting_policy: SRG, tmp_path: Path, interrupted: bool
) -> None:
    path = tmp_path / "execution.json"
    execution = SRGExecution(srg=underwriting_policy)
    history = ExecutionHistory.from_execution(execution)
    with record_execution(history, file_path=path) as recorder:
        for round_number in range(2):
            request = next_request(execution)
            assert request is not None
            answers = {
                r.predicate.id: Answer(
                    is_met=True,
                    reasoning=f"Confirmed in round {round_number}",
                )
                for r in request.predicate_requests
            }
            execution = apply_answers(execution, answers)
            recorder.record(answers)

    loaded = load_history_file(path)
    before = loaded.model_dump_json()
    assert [len(batch) for batch in loaded.batches] == [2, 2]
    execution = snapshot(loaded)
    exit_check = (
        pytest.raises(RuntimeError, match="Interrupted")
        if interrupted
        else nullcontext()
    )
    with exit_check, record_execution(loaded, file_path=path) as recorder:
        request = next_request(execution)
        assert request is not None
        answers = {
            r.predicate.id: Answer(is_met=True, reasoning="Continued")
            for r in request.predicate_requests
        }
        execution = apply_answers(execution, answers)
        recorder.record(answers)
        if interrupted:
            raise RuntimeError("Interrupted")

    resumed = load_history_file(path)
    assert loaded.model_dump_json() == before
    assert resumed.initial_answers == {}
    assert [len(batch) for batch in resumed.batches] == [2, 2, 1]
    assert resumed.batches[:2] == loaded.batches
    for step in range(3):
        assert (
            snapshot(resumed, step).model_dump() == snapshot(loaded, step).model_dump()
        )
    assert snapshot(resumed).model_dump() == execution.model_dump()


def test_resumed_history_preserves_initial_answers_and_corrections(
    simple_srg: SRG,
) -> None:
    a, b = simple_srg.predicates
    execution = SRGExecution(
        srg=simple_srg, answers={a: Answer(is_met=True, reasoning="Initial")}
    )
    history = ExecutionHistory.from_execution(execution)
    with record_execution(history) as recorder:
        recorder.record({b: Answer(is_met=True, reasoning="First batch")})
    history = ExecutionHistory.model_validate_json(
        recorder.export_history().model_dump_json()
    )
    before = history.model_dump_json()
    with record_execution(history) as recorder:
        recorder.record({a: Answer(is_met=False, reasoning="Correction")})
    updated = recorder.export_history()
    assert history.model_dump_json() == before
    assert snapshot(updated, 0).model_dump() == execution.model_dump()
    assert snapshot(updated, 1).answers[a].is_met is True
    assert snapshot(updated).answers[a].is_met is False
    assert snapshot(updated).answers[a].reasoning == "Correction"
    assert [set(batch) for batch in updated.batches] == [{b}, {a}]


def test_history_seed_and_resumed_recorder_own_their_data(simple_srg: SRG) -> None:
    a, b = simple_srg.predicates
    execution = SRGExecution(
        srg=simple_srg,
        answers={a: Answer(is_met=True, reasoning="Initial")},
    )
    history = ExecutionHistory.from_execution(execution)
    before = history.model_dump_json()
    assert history.model_dump_json() == before
    with record_execution(history) as recorder:
        recorder.record({b: Answer(is_met=True, reasoning="Batch")})
    history = recorder.export_history()
    before = history.model_dump_json()
    with record_execution(history) as resumed:
        history.initial_answers.clear()
        history.batches[0].clear()
        assert resumed.export_history().model_dump_json() == before
        exported = resumed.export_history()
        exported.batches[0].clear()
        assert resumed.export_history().model_dump_json() == before


SURROGATE_SRG = compile_srg_string(
    'predicate a: "A?"\npredicate b: "B?"\noutcome y: "Y"\npath p: all(a, b) => y\n'
)
CUT_REPLY = json.loads('{"is_met": true, "reasoning": "Looks fine \\ud83d"}')


def test_an_unencodable_answer_is_rejected_when_recorded_and_earlier_batches_save(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.json"
    history = ExecutionHistory.from_execution(SRGExecution(srg=SURROGATE_SRG))

    with (
        pytest.raises(ValueError, match="'b'.*not valid Unicode") as error,
        record_execution(history, file_path=path) as recorder,
    ):
        recorder.record({"a": Answer(is_met=True, reasoning="first batch")})
        recorder.record({"b": Answer(**CUT_REPLY)})

    assert "Looks fine" not in str(error.value)
    saved = load_history_file(path)
    assert [list(batch) for batch in saved.batches] == [["a"]]


def test_an_unencodable_initial_answer_is_rejected() -> None:
    execution = SRGExecution(srg=SURROGATE_SRG, answers={"a": Answer(**CUT_REPLY)})

    with pytest.raises(ValueError, match="'a'"):
        ExecutionHistory.from_execution(execution)


def test_paired_surrogates_record_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    with record_execution(
        ExecutionHistory(srg=SURROGATE_SRG), file_path=path
    ) as recorder:
        recorder.record({"a": Answer(is_met=True, reasoning="Looks fine \U0001f600")})

    assert load_history_file(path).batches[0]["a"].reasoning == "Looks fine \U0001f600"


def test_rejecting_an_initial_answer_does_not_echo_its_text() -> None:
    execution = SRGExecution(srg=SURROGATE_SRG, answers={"a": Answer(**CUT_REPLY)})

    with pytest.raises(ValueError) as error:
        ExecutionHistory.from_execution(execution)

    assert "Looks fine" not in str(error.value)


def test_record_saves_every_batch_before_returning(
    simple_srg: SRG, tmp_path: Path
) -> None:
    path = tmp_path / "case.json"
    a, b = simple_srg.predicates

    with record_execution(ExecutionHistory(srg=simple_srg), file_path=path) as recorder:
        recorder.record({a: Answer(is_met=True, reasoning="Yes")})
        assert len(load_history_file(path).batches) == 1

        recorder.record({b: Answer(is_met=True, reasoning="Yes")})
        assert len(load_history_file(path).batches) == 2
        assert [p.name for p in tmp_path.iterdir()] == ["case.json"]


def test_a_batch_that_cannot_be_saved_is_not_recorded(
    simple_srg: SRG, tmp_path: Path
) -> None:
    a = next(iter(simple_srg.predicates))
    recorder = ExecutionRecorder(
        ExecutionHistory(srg=simple_srg), file_path=tmp_path / "missing" / "case.json"
    )

    with pytest.raises(FileNotFoundError):
        recorder.record({a: Answer(is_met=True, reasoning="Yes")})

    assert recorder.export_history().batches == ()


@pytest.mark.parametrize("location", ["initial_answers", "batches"])
def test_history_rejects_extra_answer_fields(simple_srg: SRG, location: str) -> None:
    answer = {"is_met": True, "reasoning": "r", "confidence": 0.9}
    batch = {next(iter(simple_srg.predicates)): answer}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExecutionHistory.model_validate(
            {
                "srg": simple_srg,
                location: batch if location == "initial_answers" else [batch],
            }
        )
