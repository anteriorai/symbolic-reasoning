"""Exercise the agent tools over a host-owned execution store."""

import asyncio
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from symbolic_reasoning import SRG, Answer, Coverage, SRGExecution, compile_srg_string
from symbolic_reasoning.tools import (
    TOOLS,
    StoredExecution,
    ToolError,
    get_predicate_requests,
    get_predicates,
    get_reasoning_trace,
    submit_answers,
)
from tests.test_coverage import denial_srg


class LogStore:
    """Executions kept as their starting graph and a log of saved answer batches."""

    def __init__(
        self, srgs: Mapping[str, SRG], coverage: Coverage = Coverage.MINIMAL
    ) -> None:
        self.srgs = dict(srgs)
        self.coverage = coverage
        self.log: dict[str, list[dict[str, Answer]]] = {i: [] for i in srgs}

    async def load(self, execution_id: str) -> StoredExecution:
        if execution_id not in self.srgs:
            raise ToolError(f"Unknown execution: {execution_id}")
        answers = {k: v for batch in self.log[execution_id] for k, v in batch.items()}
        return StoredExecution(
            execution=SRGExecution(srg=self.srgs[execution_id], answers=answers),
            coverage=self.coverage,
        )

    async def save_answers(
        self, execution_id: str, answers: Mapping[str, Answer]
    ) -> StoredExecution:
        self.log[execution_id].append(dict(answers))
        return await LogStore.load(self, execution_id)


class OverlappingStore(LogStore):
    """Holds each load until two submissions have loaded, so neither sees the other."""

    def __init__(self, srgs: Mapping[str, SRG]) -> None:
        super().__init__(srgs)
        self.both_loaded = asyncio.Barrier(2)

    async def load(self, execution_id: str) -> StoredExecution:
        stored = await super().load(execution_id)
        await self.both_loaded.wait()
        return stored


async def test_submissions_are_saved_and_resume_on_later_calls(simple_srg: SRG) -> None:
    store = LogStore({"run": simple_srg})
    first = (await get_predicate_requests(store, "run")).request
    assert first is not None
    asked = first.predicate_requests[0].predicate.id
    answers = {asked: Answer(is_met=True, reasoning="Evidence")}

    progress = await submit_answers(store, "run", answers)

    assert store.log == {"run": [answers]}
    assert await get_predicate_requests(store, "run") == progress


@pytest.mark.parametrize("coverage", list(Coverage))
async def test_outcomes_arrive_with_the_resolved_decision(coverage: Coverage) -> None:
    srg, ids = denial_srg()
    store = LogStore({"run": srg}, coverage)
    assert (await get_predicate_requests(store, "run")).outcomes is None

    progress = await submit_answers(
        store, "run", {ids[0]: Answer(is_met=False, reasoning="Failed")}
    )

    assert [o.description for o in progress.outcomes or []] == ["DENIED"]
    # Reachable coverage keeps asking after the decision is resolved.
    assert (progress.request is None) is (coverage is Coverage.MINIMAL)


async def test_overlapping_submissions_report_the_committed_execution() -> None:
    srg = compile_srg_string(
        'predicate a: "A?"\npredicate b: "B?"\noutcome ok: "Approved"\n'
        "path yes: a => b => ok\n"
    )
    store = OverlappingStore({"run": srg})

    responses = await asyncio.gather(
        *(
            submit_answers(store, "run", {p: Answer(is_met=True, reasoning="r")})
            for p in ("a", "b")
        )
    )

    # Each reports what was committed when it saved, so the later one sees both.
    progress = dict(zip(("a", "b"), responses, strict=True))
    saved_first, saved_last = (next(iter(batch)) for batch in store.log["run"])
    earlier = progress[saved_first].request
    assert earlier is not None
    assert [r.predicate.id for r in earlier.predicate_requests] == [saved_last]
    assert progress[saved_last].request is None
    assert [o.id for o in progress[saved_last].outcomes or []] == ["ok"]


async def test_invalid_answers_never_reach_the_store(simple_srg: SRG) -> None:
    store = LogStore({"run": simple_srg})
    with pytest.raises(ToolError, match=r"not in the SRG \(1\)") as error:
        await submit_answers(
            store,
            "run",
            {"not_in_graph": Answer(is_met=True, reasoning="r")},
        )
    assert "not_in_graph" not in str(error.value)
    assert store.log == {"run": []}


async def test_unresolved_decisions_tell_the_agent_what_to_call(
    simple_srg: SRG,
) -> None:
    with pytest.raises(ToolError, match="get_predicate_requests"):
        await get_reasoning_trace(LogStore({"run": simple_srg}), "run")


async def test_predicates_come_with_their_saved_answers() -> None:
    srg, ids = denial_srg()
    store = LogStore({"run": srg})
    failed = Answer(is_met=False, reasoning="Failed")
    await submit_answers(store, "run", {ids[0]: failed})

    lookup = await get_predicates(store, "run", ids[:2])

    assert [(i, e.predicate.id, e.answer) for i, e in lookup.predicates.items()] == [
        (ids[0], ids[0], failed),
        (ids[1], ids[1], None),
    ]
    with pytest.raises(ToolError, match="nope"):
        await get_predicates(store, "run", ["nope"])


async def test_bound_tools_take_the_agents_arguments(simple_srg: SRG) -> None:
    store = LogStore({"run": simple_srg})
    [submit] = [s for s in TOOLS if s.name == "submit_answers"]
    first = (await get_predicate_requests(store, "run")).request
    assert first is not None
    asked = first.predicate_requests[0].predicate.id

    await submit.bind(store)(
        execution_id="run",
        answers={asked: {"is_met": True, "reasoning": "Evidence"}},
    )

    assert store.log == {"run": [{asked: Answer(is_met=True, reasoning="Evidence")}]}


async def test_bound_tools_reject_bad_arguments_without_echoing_them(
    simple_srg: SRG,
) -> None:
    store = LogStore({"run": simple_srg})
    [submit] = [s for s in TOOLS if s.name == "submit_answers"]

    with pytest.raises(ToolError, match="is_met: bool_type") as rejected:
        await submit.bind(store)(
            execution_id="run", answers={"p": {"is_met": "maybe", "reasoning": "r"}}
        )

    assert "maybe" not in str(rejected.value)
    assert store.log == {"run": []}


async def test_store_failures_are_not_reported_as_bad_arguments(
    simple_srg: SRG,
) -> None:
    class CorruptStore(LogStore):
        async def load(self, execution_id: str) -> StoredExecution:
            return StoredExecution.model_validate({})

    [requests] = [s for s in TOOLS if s.name == "get_predicate_requests"]
    with pytest.raises(ValidationError):
        await requests.bind(CorruptStore({"run": simple_srg}))(execution_id="run")


def test_specs_describe_what_the_agent_supplies() -> None:
    specs = {s.name: s for s in TOOLS}
    submit = specs["submit_answers"]
    assert submit.input_schema["required"] == ["execution_id", "answers"]
    assert "store" not in submit.input_schema["properties"]
    assert submit.output_schema["title"] == "ExecutionProgress"
    assert submit.description.startswith("Submit answers")
    assert submit.hints.destructive and submit.hints.idempotent
    assert all(s.hints.read_only for n, s in specs.items() if n.startswith("get_"))
    assert specs.keys() == {
        "get_predicate_requests",
        "submit_answers",
        "get_reasoning_trace",
        "get_predicates",
    }
