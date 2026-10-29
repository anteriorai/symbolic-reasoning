"""MCP host for the SRG agent tools, keeping graphs and executions in memory."""

from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from uuid import uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

import symbolic_reasoning as core
from symbolic_reasoning import SRG, Answer, Coverage, SRGExecution, tools
from symbolic_reasoning.tools import (
    CoverageArgument,
    StartedExecution,
    StoredExecution,
    ToolHints,
)

INSTRUCTIONS = (
    "Use list_srgs, then start_execution to get an execution ID and the first request. "
    + tools.INSTRUCTIONS
)


class SRGCatalog(BaseModel):
    """The SRG IDs available to start executions."""

    srg_ids: list[str]


class MemoryExecutionStore:
    """Executions that last as long as this object.

    Its methods never suspend, so a tool's load and save are not interleaved
    with another call's.
    """

    def __init__(self) -> None:
        self.executions: dict[str, StoredExecution] = {}

    async def load(self, execution_id: str) -> StoredExecution:
        if (stored := self.executions.get(execution_id)) is None:
            raise tools.ToolError(
                f"Unknown execution: {execution_id}. "
                "Call start_execution with an ID from list_srgs to start a new execution."
            )
        return stored

    async def save_answers(
        self, execution_id: str, answers: Mapping[str, Answer]
    ) -> StoredExecution:
        stored = self.executions[execution_id]
        committed = StoredExecution(
            execution=core.apply_answers(stored.execution, answers),
            coverage=stored.coverage,
        )
        self.executions[execution_id] = committed
        return committed


def _raising_tool_errors[**P, R](
    fn: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def tool(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except tools.ToolError as exc:
            raise ToolError(str(exc)) from exc

    return tool


def create_srg_mcp(*, srgs: Mapping[str, SRG]) -> MCPServer:
    """Create a local MCP server over a copy of `srgs`.

    Executions last for this server's lifetime.
    """
    graphs = dict(srgs)
    store = MemoryExecutionStore()

    async def list_srgs() -> SRGCatalog:
        """List available SRG IDs."""
        return SRGCatalog(srg_ids=sorted(graphs))

    async def start_execution(
        srg_id: str, coverage: CoverageArgument = Coverage.MINIMAL
    ) -> StartedExecution:
        """Start an execution and return its ID, first request and resolution status."""
        if (srg := graphs.get(srg_id)) is None:
            raise tools.ToolError(
                f"Unknown SRG: {srg_id}. Call list_srgs for available IDs."
            )
        execution_id = uuid4().hex
        stored = StoredExecution(execution=SRGExecution(srg=srg), coverage=coverage)
        store.executions[execution_id] = stored
        first = tools.progress(stored)
        return StartedExecution(
            execution_id=execution_id, request=first.request, outcomes=first.outcomes
        )

    server = MCPServer("SRG", instructions=INSTRUCTIONS)

    def add(
        fn: Callable[..., Awaitable[object]],
        name: str,
        hints: ToolHints,
        description: str | None = None,
    ) -> None:
        server.add_tool(
            _raising_tool_errors(fn),
            name=name,
            description=description,
            annotations=ToolAnnotations(
                read_only_hint=hints.read_only,
                destructive_hint=hints.destructive,
                idempotent_hint=hints.idempotent,
                open_world_hint=False,
            ),
        )

    add(
        list_srgs,
        "list_srgs",
        ToolHints(read_only=True, destructive=False, idempotent=True),
    )
    add(
        start_execution,
        "start_execution",
        ToolHints(read_only=False, destructive=False, idempotent=False),
    )
    for spec in tools.TOOLS:
        add(spec.bind(store), spec.name, spec.hints, spec.description)
    return server
