"""Exercise agent-facing schemas, state transitions, and traces through MCP."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult, TextContent

from symbolic_reasoning import SRG, Coverage, compile_srg_file
from symbolic_reasoning.mcp import create_srg_mcp
from symbolic_reasoning.tools import TOOLS
from tests.scenarios import COMPLEX_SRG_O1, make_complex_srg
from tests.test_coverage import denial_srg


async def call(client: Client, tool: str, **arguments: Any) -> dict[str, Any]:
    result = await client.call_tool(tool, arguments)
    assert isinstance(result, CallToolResult)
    assert not result.is_error, result.content
    # Hosts that read only text content must see every result, including empty ones.
    assert result.content and all(
        isinstance(c, TextContent) and c.text for c in result.content
    )
    assert result.structured_content is not None
    return dict(result.structured_content)


async def ask(client: Client, tool: str, **arguments: Any) -> Any:
    """Return the predicate request from a request tool."""
    return (await call(client, tool, **arguments))["request"]


async def test_complex_solve_and_traces() -> None:
    server = create_srg_mcp(srgs={"complex": make_complex_srg()})
    async with Client(server, raise_exceptions=True) as client:
        available = await client.list_tools()
        assert {t.name for t in available.tools} == {
            "list_srgs",
            "start_execution",
            "get_predicate_requests",
            "submit_answers",
            "get_reasoning_trace",
            "get_predicates",
        }
        assert all(t.output_schema for t in available.tools)
        hints = {
            t.name: (
                t.annotations.read_only_hint,
                t.annotations.destructive_hint,
                t.annotations.idempotent_hint,
            )
            for t in available.tools
            if t.annotations
        }
        assert hints["start_execution"] == (False, False, False)
        assert hints["submit_answers"] == (False, True, True)
        assert hints["get_reasoning_trace"][0] is True
        catalog = await call(client, "list_srgs")
        assert catalog == {"srg_ids": ["complex"]}
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="complex"
        )
        execution_id = started["execution_id"]
        progress = started["request"]
        assert started["outcomes"] is None
        unresolved = await client.call_tool(
            "get_reasoning_trace", {"execution_id": execution_id}
        )
        assert isinstance(unresolved, CallToolResult) and unresolved.is_error
        for step in COMPLEX_SRG_O1.steps:
            requests = progress["predicate_requests"]
            assert [
                r["predicate"]["id"] for r in requests
            ] == step.expected_predicate_ids
            for request in requests:
                if request["predicate"]["id"] == "P9":
                    assert [
                        s["predicate_id"] for s in request["contextual_predicates"]
                    ] == [
                        "P1",
                        "P5",
                        "P6",
                    ]
            progress = await ask(
                client,
                "submit_answers",
                execution_id=execution_id,
                answers={
                    p: {"is_met": value, "reasoning": "Test evidence"}
                    for p, value in reversed(
                        list(
                            zip(step.expected_predicate_ids, step.answers, strict=True)
                        )
                    )
                },
            )
        assert progress is None
        final = await call(client, "get_predicate_requests", execution_id=execution_id)
        assert [o["description"] for o in final["outcomes"]] == ["O1"]
        trace = await call(client, "get_reasoning_trace", execution_id=execution_id)
        assert [p["outcome_id"] for p in trace["outcome_paths"]] == [
            final["outcomes"][0]["id"]
        ]
        assert len(trace["all_paths"]) == 2
        steps = trace["outcome_paths"][0]["steps"]
        traced = [s["predicate_id"] for s in steps]
        lookup = await call(
            client, "get_predicates", execution_id=execution_id, predicate_ids=traced
        )
        entries = lookup["predicates"]
        assert list(entries) == traced
        assert {e["answer"]["reasoning"] for e in entries.values()} == {"Test evidence"}
        assert [entries[i]["answer"]["is_met"] for i in traced] == [
            s["is_met"] for s in steps
        ]
        unanswered = await call(
            client, "get_predicates", execution_id=execution_id, predicate_ids=["P3"]
        )
        assert unanswered["predicates"]["P3"]["answer"] is None
        missing = await client.call_tool(
            "get_predicates",
            {"execution_id": execution_id, "predicate_ids": ["P1", "nope"]},
        )
        assert isinstance(missing, CallToolResult) and missing.is_error
        assert "['nope']" in str(missing.content)


@pytest.mark.parametrize("coverage", list(Coverage))
async def test_coverage_and_resume(coverage: Coverage) -> None:
    srg, ids = denial_srg()
    server = create_srg_mcp(srgs={"denial": srg})
    async with Client(server) as client:
        started = await call(
            client, "start_execution", coverage=coverage.value, srg_id="denial"
        )
        execution_id = started["execution_id"]
        args = {
            "execution_id": execution_id,
            "answers": {ids[0]: {"is_met": False, "reasoning": "Failed"}},
        }
        submitted = await call(client, "submit_answers", **args)
        second = submitted["request"]
        assert (second is None) is (coverage is Coverage.MINIMAL)
        # Reachable coverage still has questions after the decision is resolved.
        assert [o["description"] for o in submitted["outcomes"]] == ["DENIED"]
        assert (await call(client, "get_reasoning_trace", execution_id=execution_id))[
            "outcome_paths"
        ]
        assert (
            await ask(
                client,
                "get_predicate_requests",
                execution_id=execution_id,
            )
            == second
        )
        args["answers"][ids[0]]["is_met"] = True
        revised = await call(client, "submit_answers", **args)
        assert revised["outcomes"] is None
        assert [
            r["predicate"]["id"] for r in revised["request"]["predicate_requests"]
        ] == [ids[1]]
        unresolved = await client.call_tool(
            "get_reasoning_trace", {"execution_id": execution_id}
        )
        assert isinstance(unresolved, CallToolResult) and unresolved.is_error


@pytest.mark.parametrize("kind", ["unknown", "invalid_answer"])
async def test_bad_answers_leave_storage_unchanged(kind: str) -> None:
    async with Client(create_srg_mcp(srgs={"complex": make_complex_srg()})) as client:
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="complex"
        )
        execution_id = started["execution_id"]
        first = started["request"]
        answers: dict[str, Any] = {
            p: {"is_met": True, "reasoning": "r"} for p in ["P1", "P12"]
        }
        if kind == "unknown":
            answers["not_in_graph"] = answers.pop("P1")
        else:
            answers["P1"]["is_met"] = "unknown"
        result = await client.call_tool(
            "submit_answers",
            {"execution_id": execution_id, "answers": answers},
        )
        assert isinstance(result, CallToolResult) and result.is_error
        assert (
            await ask(
                client,
                "get_predicate_requests",
                execution_id=execution_id,
            )
            == first
        )


async def test_submissions_match_library_semantics() -> None:
    async with Client(create_srg_mcp(srgs={"complex": make_complex_srg()})) as client:
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="complex"
        )
        execution_id = started["execution_id"]
        assert (
            await ask(
                client,
                "submit_answers",
                execution_id=execution_id,
                answers={},
            )
            == started["request"]
        )

        # P2 is not ready until P1 is answered; its answer is saved and given
        # to P1 as context.
        ahead = {"P2": {"is_met": True, "reasoning": "r"}}
        request = await ask(
            client,
            "submit_answers",
            execution_id=execution_id,
            answers=ahead,
        )
        assert [
            (
                r["predicate"]["id"],
                [s["predicate_id"] for s in r["contextual_predicates"]],
            )
            for r in request["predicate_requests"]
        ] == [("P1", ["P2"]), ("P12", [])]
        batch = {"P1": {"is_met": True, "reasoning": "r"}}
        request = await ask(
            client,
            "submit_answers",
            execution_id=execution_id,
            answers=batch,
        )
        assert "P2" not in [r["predicate"]["id"] for r in request["predicate_requests"]]

        # Resending a saved batch, as after a lost response, changes nothing.
        assert (
            await ask(
                client,
                "submit_answers",
                execution_id=execution_id,
                answers=batch,
            )
            == request
        )


async def test_a_partial_batch_leaves_the_rest_outstanding() -> None:
    async with Client(create_srg_mcp(srgs={"complex": make_complex_srg()})) as client:
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="complex"
        )
        execution_id = started["execution_id"]

        request = await ask(
            client,
            "submit_answers",
            execution_id=execution_id,
            answers={"P1": {"is_met": True, "reasoning": "r"}},
        )

        # P12 was never answered and comes back; P2 is newly unlocked by P1.
        assert [r["predicate"]["id"] for r in request["predicate_requests"]] == [
            "P2",
            "P12",
        ]
        assert request["predicate_requests"][0]["contextual_predicates"] == [
            {"predicate_id": "P1", "is_met": True}
        ]
        assert request["predicates"] == request["answers"] == {}


@pytest.mark.parametrize("suffix", [".json", ".srg"])
async def test_stdio_cli(tmp_path: Path, simple_srg: SRG, suffix: str) -> None:
    policy_path = tmp_path / f"simple{suffix}"
    policy_path.write_text(
        'predicate p: "Evidence?"\noutcome ok: "Approved"\npath yes: p => ok\n'
        if suffix == ".srg"
        else simple_srg.model_dump_json()
    )
    (tmp_path / "replay.json").write_text('{"not_a_policy": true}')
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "symbolic_reasoning.mcp",
            "--srg",
            "simple",
            str(policy_path),
        ],
    )
    async with Client(params, read_timeout_seconds=10) as client:
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="simple"
        )
        execution_id = started["execution_id"]
        request = started["request"]
        assert request["predicate_requests"]
        while request is not None:
            request = await ask(
                client,
                "submit_answers",
                execution_id=execution_id,
                answers={
                    r["predicate"]["id"]: {"is_met": True, "reasoning": "Evidence"}
                    for r in request["predicate_requests"]
                },
            )


async def test_server_executions_are_independent(simple_srg: SRG) -> None:
    async with Client(create_srg_mcp(srgs={"simple": simple_srg})) as first:
        started = await call(
            first, "start_execution", coverage="minimal", srg_id="simple"
        )
        execution_id = started["execution_id"]
    async with Client(create_srg_mcp(srgs={"simple": simple_srg})) as second:
        result = await second.call_tool(
            "get_predicate_requests",
            {"execution_id": execution_id},
        )
        assert isinstance(result, CallToolResult) and result.is_error
        assert "start_execution" in str(result.content)


async def test_concurrent_partial_submissions_preserve_both_answers() -> None:
    async with Client(create_srg_mcp(srgs={"complex": make_complex_srg()})) as client:
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="complex"
        )
        execution_id = started["execution_id"]
        await asyncio.gather(
            *(
                call(
                    client,
                    "submit_answers",
                    execution_id=execution_id,
                    answers={predicate_id: {"is_met": True, "reasoning": "Evidence"}},
                )
                for predicate_id in ("P1", "P12")
            )
        )
        request = await ask(
            client,
            "get_predicate_requests",
            execution_id=execution_id,
        )
        assert [r["predicate"]["id"] for r in request["predicate_requests"]] == [
            "P2",
            "P13",
        ]


async def test_executions_are_independent() -> None:
    graph, ids = denial_srg()
    server = create_srg_mcp(srgs={"denial": graph})
    async with Client(server) as client:
        first = await call(
            client, "start_execution", coverage="minimal", srg_id="denial"
        )
        second = await call(
            client, "start_execution", coverage="minimal", srg_id="denial"
        )
        assert first["execution_id"] != second["execution_id"]
        assert first["request"] == second["request"]
        await call(
            client,
            "submit_answers",
            execution_id=first["execution_id"],
            answers={ids[0]: {"is_met": False, "reasoning": "Evidence"}},
        )
        assert (
            await ask(
                client,
                "get_predicate_requests",
                execution_id=second["execution_id"],
            )
            == second["request"]
        )


@pytest.mark.parametrize("name", ["msk-review", "underwriting"])
async def test_shared_policy_starts(name: str) -> None:
    policy_path = Path(__file__).parents[2] / "examples" / "data" / name / "policy.srg"
    graph = compile_srg_file(policy_path)
    async with Client(create_srg_mcp(srgs={name: graph})) as client:
        started = await call(client, "start_execution", coverage="minimal", srg_id=name)
        assert started["request"]["predicate_requests"]
        assert (
            await ask(
                client,
                "get_predicate_requests",
                execution_id=started["execution_id"],
            )
            == started["request"]
        )


async def test_no_outcome_is_resolved_with_explored_paths() -> None:
    policy_path = Path(__file__).parents[2] / "examples/data/msk-review/policy.srg"
    graph = compile_srg_file(policy_path)
    async with Client(create_srg_mcp(srgs={"msk": graph})) as client:
        started = await call(
            client, "start_execution", coverage="minimal", srg_id="msk"
        )
        execution_id = started["execution_id"]
        completed = await call(
            client,
            "submit_answers",
            execution_id=execution_id,
            answers={
                r["predicate"]["id"]: {"is_met": False, "reasoning": "Not documented"}
                for r in started["request"]["predicate_requests"]
            },
        )
        assert completed == {"request": None, "outcomes": []}
        trace = await call(client, "get_reasoning_trace", execution_id=execution_id)
        assert trace["outcome_paths"] == []
        assert trace["all_paths"]


async def test_coverage_defaults_to_minimal() -> None:
    srg, ids = denial_srg()
    async with Client(create_srg_mcp(srgs={"denial": srg})) as client:
        started = await call(client, "start_execution", srg_id="denial")
        submitted = await call(
            client,
            "submit_answers",
            execution_id=started["execution_id"],
            answers={ids[0]: {"is_met": False, "reasoning": "Failed"}},
        )
        # Minimal stops asking once the denial is decided.
        assert submitted["request"] is None
        assert [o["description"] for o in submitted["outcomes"]] == ["DENIED"]


async def test_tools_match_the_library_specs(simple_srg: SRG) -> None:
    async with Client(create_srg_mcp(srgs={"simple": simple_srg})) as client:
        served = {t.name: t for t in (await client.list_tools()).tools}
        for spec in TOOLS:
            schema = served[spec.name].input_schema
            assert served[spec.name].description == spec.description
            assert schema["required"] == spec.input_schema["required"]
            assert schema["properties"].keys() == spec.input_schema["properties"].keys()
        result = await client.call_tool(
            "start_execution", {"srg_id": "missing", "coverage": "minimal"}
        )
        assert isinstance(result, CallToolResult) and result.is_error
        assert "list_srgs" in str(result.content)
