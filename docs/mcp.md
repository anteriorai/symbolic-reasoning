# Local SRG MCP server

The server exposes the solver as local stdio tools. An agent answers the policy's questions from case evidence; the library determines the outcomes. The server does not read case documents or call an LLM.

## Set up

From the repository root:

```bash
uv sync --extra mcp
uv run python -m symbolic_reasoning.mcp \
  --srg msk-review examples/data/msk-review/policy.srg \
  --srg underwriting examples/data/underwriting/policy.srg
```

Each `--srg ID PATH` registers one policy, from `.srg` source or compiled SRG JSON. IDs must be unique. Source compiles at startup; if any policy fails to load, the server exits with the error. To change the catalog, restart the server.

To connect a host, use the virtual environment's Python and absolute paths:

```json
{
  "mcpServers": {
    "srg": {
      "command": "/abs/path/to/repo/.venv/bin/python",
      "args": [
        "-m", "symbolic_reasoning.mcp",
        "--srg", "msk-review", "/abs/path/to/repo/examples/data/msk-review/policy.srg",
        "--srg", "underwriting", "/abs/path/to/repo/examples/data/underwriting/policy.srg"
      ]
    }
  }
}
```

With Claude Code:

```bash
claude mcp add srg -- /abs/path/to/repo/.venv/bin/python -m symbolic_reasoning.mcp \
  --srg underwriting /abs/path/to/repo/examples/data/underwriting/policy.srg
```

Give the agent the case evidence through its host, for example `examples/data/underwriting/application.md`.

## Evaluate a case

The server gives the agent instructions for this flow:

1. `list_srgs()` returns the registered IDs.
2. `start_execution(srg_id, coverage)` returns an `execution_id`, the first `request` and `outcomes`; `coverage` is optional.
3. `submit_answers(execution_id, answers)` returns the next `request`. Repeat until `request` is `null`.
4. `outcomes` is `null` until the decision is resolved, then lists the reached outcomes. `get_reasoning_trace(execution_id)` explains why.

A request lists the predicates ready to answer, the `policy_context`, and for each predicate the `contextual_predicates` already answered on the way to it. It leaves out the text of those earlier predicates; `get_predicates(execution_id, predicate_ids)` returns any predicate with its saved answer. Answers are keyed by predicate ID, and both `is_met` and `reasoning` are required:

```json
{
  "execution_id": "20bcd34158c34c2bb84d5d65724b586d",
  "answers": {
    "has_good_credit": {"is_met": true, "reasoning": "credit_score is 742."}
  }
}
```

- A request can be answered across several calls, in any order. Unanswered predicates are asked again alongside newly unlocked ones, and answers for predicates not yet requested are saved too.
- Resubmitting a predicate replaces its answer, so retrying a batch is safe. `get_predicate_requests(execution_id)` shows what remains.
- Changing an earlier answer can change the outcome or reopen a resolved decision, so check `outcomes` after every submission.
- Unknown predicate IDs and invalid answers reject the whole batch without changing the execution.

## Coverage

`start_execution` takes a `coverage`, `minimal` by default, which the execution keeps. `minimal` asks only what deciding the outcome requires. `reachable` also finishes the requirements on every reached branch, for a complete record; it can take more rounds, and `outcomes` can arrive while questions remain. See [Coverage](python-guide.md#coverage).

## Read the decision

A policy can reach several outcomes or none. Reaching none (`[]`) is not an implicit approval or denial; the host decides what it means.

In `get_reasoning_trace`, `outcome_paths` lead to each reached outcome and `all_paths` lists every explored path, including dead ends, so it shows where evaluation stopped. Each step is a `predicate_id` and `is_met`. The trace is a logical justification, not a chronological log of tool calls.

Executions live in memory. After a server restart, start a new execution.

## Embed in Python

```python
from symbolic_reasoning import compile_srg_file
from symbolic_reasoning.mcp import create_srg_mcp

server = create_srg_mcp(srgs={"underwriting": compile_srg_file("policy.srg")})
server.run(transport="stdio")
```

Each server copies the catalog it is given and keeps its own executions. Overlapping tool calls cannot overwrite each other's answers.

To use the tools in another agent host, see [Use with agents](python-guide.md#use-with-agents).
