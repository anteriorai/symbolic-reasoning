"""Viewer projections agree with execution semantics; exports stay self-contained."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from symbolic_reasoning import (
    Answer,
    ExecutionHistory,
    SRGBuilder,
    SRGExecution,
    compile_srg_file,
    is_resolved,
    load_history_file,
    reasoning_trace,
    save_history_file,
    snapshot,
)
from symbolic_reasoning.models import SRG, AllStrategy, evaluate_symbol
from symbolic_reasoning.recording import ExecutionRecorder
from symbolic_reasoning.viewer import _history_data, save_history_html


def _expand_trace(trace: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """Resolve exported references back into the public runtime artifact."""
    expanded: dict[str, Any] = {
        kind: [
            {
                **({"outcome_id": path["outcome"]} if "outcome" in path else {}),
                "steps": [
                    {"predicate_id": id_, "is_met": answers[id_]["is_met"]}
                    for id_ in path["steps"]
                ],
            }
            for path in paths
        ]
        for kind, paths in trace.items()
    }
    return expanded


def test_frames_follow_false_edges_and_answer_corrections(branching_srg: SRG) -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=branching_srg))
    )
    recorder.record({"P1": Answer(is_met=False, reasoning="No")})
    recorder.record({"P1": Answer(is_met=True, reasoning="Corrected")})
    history = recorder.export_history()
    data = _history_data(history)
    assert len(data["frames"]) == 3
    for step, frame in enumerate(data["frames"]):
        execution = snapshot(history, step)
        assert frame["resolved"] == is_resolved(execution)
        if step:
            answers = {**data["initial_answers"]}
            for batch in data["batches"][:step]:
                answers.update(batch)
            assert _expand_trace(frame["trace"], answers) == (
                reasoning_trace(execution).model_dump(mode="json")
            )
            assert frame["applied"] == ["P1"]
            taken = [branching_srg.edges[key] for key in frame["taken"]]
            assert len(taken) == 2
            assert next(edge for edge in taken if edge.source != "Root").condition == (
                step == 2
            )
        else:
            assert frame["trace"] is None
            assert frame["applied"] == []
    assert data["batches"][0]["P1"]["reasoning"] == "No"
    assert data["batches"][1]["P1"]["reasoning"] == "Corrected"


def test_known_answers_do_not_make_unrelated_paths_reachable() -> None:
    srg = SRGBuilder()
    gate = srg.add_predicate("Gate")
    shared = srg.add_predicate("Shared")
    gate_node, left, right = [srg.add_node(id_) for id_ in (gate, shared, shared)]
    srg.add_edge("Root", gate_node)
    srg.add_edge("Root", left)
    srg.add_edge(gate_node, right, condition=True)
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(
            SRGExecution(
                srg=srg.build(),
                answers={
                    gate: Answer(is_met=False, reasoning="Closed"),
                    shared: Answer(is_met=True, reasoning="Shared fact"),
                },
            )
        )
    )
    frame = _history_data(recorder.export_history())["frames"][0]
    assert frame["verdicts"][shared] is True
    assert left in frame["reached"]
    assert right not in frame["reached"]
    assert frame["resolved"]
    assert frame["trace"]["outcome_paths"] == []
    assert len(frame["trace"]["all_paths"]) == 2


@pytest.mark.parametrize("condition", [True, False])
def test_converging_paths_retain_all_traversed_edges(condition: bool) -> None:
    srg = SRGBuilder()
    a, b = srg.add_predicate("A"), srg.add_predicate("B")
    left, right = srg.add_node(a), srg.add_node(b)
    outcome = srg.add_node(srg.add_outcome("Result"))
    srg.add_edge("Root", left).add_edge("Root", right)
    srg.add_edge(left, outcome, condition=condition)
    srg.add_edge(right, outcome, condition=condition)
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(
            SRGExecution(
                srg=srg.build(),
                answers={
                    id_: Answer(is_met=condition, reasoning="Fact") for id_ in (a, b)
                },
            )
        )
    )
    frame = _history_data(recorder.export_history())["frames"][0]
    assert set(frame["taken"]) == set(srg.edges)
    assert len(frame["trace"]["outcome_paths"]) == 2


def test_nested_negation_and_short_circuit_preserve_runtime_verdicts() -> None:
    srg = SRGBuilder()
    a = srg.add_predicate("A?", id="a")
    b = srg.add_predicate("B?", id="b")
    both = srg.add_aggregator(AllStrategy(), True, [a, b], name="both")
    negation = srg.add_aggregator(AllStrategy(), False, [both])
    condition = srg.add_node(negation)
    outcome = srg.add_node(srg.add_outcome("Yes"))
    srg.add_edge("Root", condition).add_edge(condition, outcome)
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=srg.build()))
    )
    recorder.record({"a": Answer(is_met=False, reasoning="No")})
    recorder.record({"b": Answer(is_met=True, reasoning="Extra")})
    history = recorder.export_history()
    frames = _history_data(history)["frames"]
    assert [f["resolved"] for f in frames] == [False, True, True]
    for step, frame in enumerate(frames):
        execution = snapshot(history, step)
        for id_ in srg.aggregators:
            assert frame["verdicts"][id_] == evaluate_symbol(execution, id_)
    assert frames[2]["applied"] == ["b"]


def test_html_is_offline_and_escapes_untrusted_content(tmp_path: Path) -> None:
    attack = '</script><script>window.attacked = true</script><img src="https://invalid.test/x">'
    srg = SRGBuilder()
    p = srg.add_predicate(attack)
    srg.add_edge("Root", srg.add_node(p))

    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(
            SRGExecution(
                srg=srg.build(),
                answers={p: Answer(is_met=True, reasoning=attack)},
            )
        )
    )
    file = tmp_path / "replay.html"
    save_history_html(recorder.export_history(), file, title="</title>@@SCRIPT@@")
    html = file.read_text()
    assert attack not in html
    assert "&lt;/title&gt;@@SCRIPT@@" in html
    embedded = re.search(
        r'<script id="history-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert embedded
    data = json.loads(embedded.group(1))
    assert data["initial_answers"][p]["reasoning"] == attack
    assert data["graph"]["predicates"][p]["question"] == attack
    assert not re.search(r"<(?:script|link)[^>]+(?:src|href)=", html)
    assert "Permission is hereby granted" in html


def test_empty_history_and_empty_batch() -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=SRGBuilder().build()))
    )
    recorder.record({})
    frames = _history_data(recorder.export_history())["frames"]
    assert len(frames) == 2
    assert all(frame["resolved"] and frame["applied"] == [] for frame in frames)


def test_cli_opens_a_saved_recording_without_an_agent(
    branching_srg: SRG, tmp_path: Path
) -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(SRGExecution(srg=branching_srg))
    )
    recorder.record({"P1": Answer(is_met=False, reasoning="Recorded evidence")})
    recording = tmp_path / "execution.json"
    save_history_file(recorder.export_history(), recording)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "symbolic_reasoning.viewer",
            str(recording),
            "--title",
            "Recorded review",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    output = tmp_path / "replay.html"
    assert str(output) in result.stdout
    html = output.read_text()
    assert "<title>Recorded review</title>" in html
    embedded = re.search(
        r'<script id="history-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert embedded
    data = json.loads(embedded.group(1))
    frames = data["frames"]
    assert len(frames) == 2
    assert data["batches"][0]["P1"]["reasoning"] == "Recorded evidence"
    assert frames[1]["resolved"]


def test_projection_stores_answer_content_once_and_does_not_mutate_history(
    branching_srg: SRG,
) -> None:
    recorder = ExecutionRecorder(
        ExecutionHistory.from_execution(
            SRGExecution(
                srg=branching_srg,
                answers={
                    "P1": Answer(
                        is_met=False,
                        reasoning="Initial evidence " * 200,
                    )
                },
            )
        )
    )
    recorder.record(
        {
            "P1": Answer(
                is_met=True,
                reasoning="Corrected evidence " * 200,
            ),
        },
    )
    for _ in range(20):
        recorder.record({})
    history = recorder.export_history()
    before = history.model_dump_json()
    data = _history_data(history)
    encoded = json.dumps(data)
    assert encoded.count("Initial evidence") == 200
    assert encoded.count("Corrected evidence") == 200
    assert history.model_dump_json() == before
    answers = dict(data["initial_answers"])
    for step, frame in enumerate(data["frames"]):
        if step:
            answers.update(data["batches"][step - 1])
        execution = snapshot(history, step)
        assert answers == {
            id_: answer.model_dump(mode="json")
            for id_, answer in execution.answers.items()
        }
        assert _expand_trace(frame["trace"], answers) == (
            reasoning_trace(execution).model_dump(mode="json")
        )


def test_bundled_replay_loads_without_a_builder(tmp_path: Path) -> None:
    recording = Path(__file__).parents[1] / "examples/data/msk-review/replay.json"
    history = load_history_file(recording)
    assert history.srg == compile_srg_file(recording.with_name("policy.srg"))
    final = snapshot(history)
    assert is_resolved(final)
    assert {key: item.description for key, item in history.srg.outcomes.items()} == {
        "approved": "Approved",
        "needs_review": "Needs review",
    }
    children: dict[str, list[str]] = {key: [] for key in history.srg.nodes}
    for edge in history.srg.edges.values():
        children[edge.source].append(edge.target)

    def depth(node: str) -> int:
        return 1 + max((depth(child) for child in children[node]), default=0)

    assert len(children["Root"]) == 4
    assert depth("Root") == 5
    seen: set[str] = set()
    for batch in history.batches:
        assert not seen.intersection(batch)
        seen.update(batch)
    assert len(history.batches) == 6
    traces = reasoning_trace(final).outcome_paths
    assert [path.outcome_id for path in traces].count("approved") == 3
    assert [path.outcome_id for path in traces].count("needs_review") == 1
    data = _history_data(history)
    previous: set[str] = set()
    for frame in data["frames"]:
        reached = {
            history.srg.nodes[key].item_id for key in frame["reached"]
        }.intersection(history.srg.outcomes)
        assert previous <= reached
        previous = reached
    output = tmp_path / "replay.html"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "symbolic_reasoning.viewer",
            str(recording),
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert '"approved"' in output.read_text()


def _run_viewer(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "symbolic_reasoning.viewer", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "output", ["execution.json", "./execution.json", "link.json", "hard.json"]
)
def test_viewer_refuses_to_write_over_its_recording(
    tmp_path: Path, output: str
) -> None:
    recording = tmp_path / "execution.json"
    save_history_file(ExecutionHistory(srg=SRGBuilder().build()), recording)
    (tmp_path / "link.json").symlink_to(recording)
    (tmp_path / "hard.json").hardlink_to(recording)
    before = recording.read_bytes()

    result = _run_viewer(tmp_path, "execution.json", "-o", output)

    assert result.returncode == 2
    assert "is the input recording" in result.stderr
    assert recording.read_bytes() == before


def test_viewer_writes_a_distinct_output(tmp_path: Path) -> None:
    recording = tmp_path / "execution.json"
    save_history_file(ExecutionHistory(srg=SRGBuilder().build()), recording)

    result = _run_viewer(tmp_path, "execution.json", "-o", "replay.html")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "replay.html").read_text().lower().startswith("<!doctype html>")
