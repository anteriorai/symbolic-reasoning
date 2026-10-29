# Python Guide

How to build, solve and inspect policies with the `symbolic_reasoning` package. For the `.srg` language and how evaluation works, see [The SRG language](srg-language.md).

```python
import symbolic_reasoning as sr
```

## Build

Compile a file with `compile_srg_file()` or a string with `compile_srg_string()`. Invalid source raises `ParseError`, and source that cannot compile raises `CompilerError`, each with a `loc`. `load_srg()` loads a graph compiled elsewhere, such as by `@anteriorai/srg-compiler`.

To build an SRG in code instead, use `SRGBuilder`. Symbols get generated IDs unless you pass `id=`:

```python
builder = sr.SRGBuilder()
adult = builder.add_node(builder.add_predicate("Is the applicant an adult?", id="is_adult"))
approved = builder.add_node(builder.add_outcome("Approved", id="approved"))
builder.add_edge("Root", adult).add_edge(adult, approved)
srg = builder.build()
```

## Solve

### Oracles

An oracle takes an `OracleRequest` and returns answers keyed by predicate ID. It can be sync or async; bind anything else it needs with a closure or `functools.partial`.

- `request.predicate_requests`: the questions to answer. Each has a `predicate` (`id`, `question`, `context`, and the policy's annotations) and its `contextual_predicates`: the answers already known on the branches that lead to it, as `predicate_id` and `is_met`.
- `request.predicates` and `request.answers`: each contextual predicate and its answer, listed once per request.
- `request.policy_context`: guidance for the whole policy, from its `policy_context` declaration.

Answer any subset; the rest are asked again next round. `asolve()` raises if a round answers none of the requested predicates, and passes on any exception the oracle raises.

```python
async def oracle(request: sr.OracleRequest) -> dict[str, sr.Answer]:
    answers = {}
    for predicate_request in request.predicate_requests:
        known = [
            (request.predicates[s.predicate_id], request.answers[s.predicate_id])
            for s in predicate_request.contextual_predicates
        ]
        answers[predicate_request.predicate.id] = await ask_llm(
            predicate_request.predicate, known, request.policy_context
        )
    return answers
```

An `Answer` holds only `is_met` and `reasoning`. Keep other application data in your own records, keyed by predicate ID. One predicate ID is one fact with one answer per execution; if a question means something different on different branches, give each its own ID.

### Step by step

`asolve()` runs the loop for you. To control the execution loop yourself, use `next_request()` and `apply_answers()`. Both are pure functions of the execution, so a solve can be paused, saved and resumed:

```python
execution = sr.SRGExecution(srg=srg)
while (request := sr.next_request(execution)) is not None:
    execution = sr.apply_answers(execution, await oracle(request))
```

`apply_answers()` returns a new execution and keeps earlier answers; resubmitting an ID replaces its answer. Unknown IDs and invalid answers raise `InvalidAnswerError`, whose message never includes the submitted values. `asolve()` also accepts a partial execution to resume from.

### Coverage

By default (`Coverage.MINIMAL`) a solve stops asking once the outcome is decided, so a denial cites the first requirement that failed. To collect every unmet requirement, solve with `Coverage.REACHABLE`:

```python
execution = await sr.asolve(srg, oracle, coverage=sr.Coverage.REACHABLE)
```

It answers every predicate on the branches the graph reaches, even when the answer cannot change the outcome. It never enters a branch the graph didn't take, so it cannot add an outcome.

| `all(a, b, c)` | `MINIMAL` | `REACHABLE` |
|---|---|---|
| approved | 3 questions | 3 questions |
| denied at `a` | 1 question | 3 questions |

Coverage is an argument, not part of the execution. When resuming with `next_request()`, pass it on every call; you can also resume a minimal solve with `REACHABLE` to collect more answers.

## Interpret

```python
trace = sr.reasoning_trace(execution)
trace.outcome_paths          # an OutcomePath per path that reached an outcome
trace.all_paths              # every path explored, including dead ends
sr.outcomes(execution)       # the distinct Outcome objects reached
```

Each path lists the answered predicates (`predicate_id`, `is_met`) along it; look them up in `execution.srg.predicates` and `execution.answers`. To check one outcome, test `any(o.id == "denied" for o in sr.outcomes(execution))`, or filter `outcome_paths` by `outcome_id` for its reasons.

Both functions raise `ExecutionNotResolvedError` until the graph is decided, rather than return a partial result that looks final. `sr.is_resolved(execution)` says whether it is; `next_request()` returns what to ask next. A solve driven to completion is always resolved, and resolved does not mean every predicate is answered: evaluation short-circuits.

Several paths can reach the same outcome, and a policy can reach several outcomes or none. `outcomes()` returns `[]` when no path completes; `all_paths` shows where evaluation stopped. See [Designing outcomes](srg-language.md#designing-outcomes).

## Record and replay

Record each batch of answers to a history file:

```python
history = sr.ExecutionHistory.from_execution(execution)
with sr.record_execution(history, file_path="execution.json") as recorder:
    while (request := sr.next_request(execution)) is not None:
        answers = await oracle(request)
        execution = sr.apply_answers(execution, answers)
        recorder.record(answers)
```

The file is saved when the block exits, including on an exception. Omit `file_path` to record in memory and call `recorder.export_history()`. `load_history_file()` reads a history back, `snapshot(history, n)` returns the execution after `n` batches (the latest by default), and passing a loaded history to `record_execution()` continues it.

Replay a recording as an interactive, offline HTML page:

```bash
uv run python -m symbolic_reasoning.viewer execution.json --open
```

Try it with the bundled example: `examples/data/msk-review/replay.json`. From Python, use `symbolic_reasoning.viewer.save_history_html(history, "replay.html")`.

## Use with agents

`symbolic_reasoning.tools` lets an agent work through a policy as tool calls in any agent framework; the [MCP server](mcp.md) is one host of these tools. Each entry in `TOOLS` has a name, description, input and output JSON schemas and hints to register with your framework. Each tool takes your `ExecutionStore` first, then the arguments the agent supplies, starting with the execution's ID. Bind your store for each call; the agent's schema leaves it out:

```python
from symbolic_reasoning.tools import INSTRUCTIONS, TOOLS

for spec in TOOLS:
    register(spec.name, spec.description, spec.input_schema, spec.hints)

async def call(spec, arguments):
    result = await spec.bind(my_store)(**arguments)
    return result.model_dump_json()
```

- The store loads an execution by ID as a `StoredExecution`: the execution and the coverage its requests follow. It saves answers the tools have validated and returns the execution as committed, including answers other submissions saved first. Make saving atomic if submissions can overlap.
- Starting executions, choosing their IDs and coverage, and listing graphs are the host's; the MCP server's `list_srgs` and `start_execution` are one way to do it. Return a `StartedExecution` built from `progress(stored)`, and describe a coverage argument with `CoverageArgument`.
- Tools raise `ToolError` for mistakes the agent can correct, as should the store for an unknown ID; return its message to the agent as a tool error.
- `INSTRUCTIONS` describes the workflow; give it to the agent with the tools, along with how to start an execution in your host.

To drive the questions yourself instead, use `next_request()` and `apply_answers()` ([Step by step](#step-by-step)).

## API reference

### Build

| Name | Description |
|---|---|
| `compile_srg_file(path)` / `compile_srg_string(source)` | Compile `.srg` source to an `SRG` |
| `load_srg(data)` | Load an `SRG` from a mapping or JSON text |
| `SRGBuilder` | A mutable draft: `add_predicate`, `add_outcome`, `add_aggregator`, `add_node`, `add_edge`, then `build()`; `from_srg(srg)` starts from an existing graph |
| `SRG` | A validated, read-only graph of `Predicate`s, `Outcome`s, aggregators, nodes and edges |

### Solve

| Name | Description |
|---|---|
| `asolve(srg_or_execution, oracle, *, coverage)` | Solve with an oracle, from a graph or a partial execution |
| `next_request(execution, coverage, *, hydrate_context)` | The next `OracleRequest`, or `None` once resolved; `hydrate_context=False` leaves out contextual definitions and answers |
| `apply_answers(execution, answers)` | A new execution with the answers merged and validated |
| `SRGExecution` | A graph and the answers so far |
| `Answer` | An immutable `is_met` and `reasoning` |
| `OracleRequest` / `PredicateRequest` | A round of questions, and one question with its context |
| `Oracle` / `AsyncOracle` | The oracle callables `asolve()` accepts |
| `Coverage` | `MINIMAL` (default) or `REACHABLE` |

### Interpret

| Name | Description |
|---|---|
| `reasoning_trace(execution)` | A `ReasoningTrace`: `outcome_paths` (`OutcomePath`) and `all_paths` (`TracePath`), each a list of `TraceStep`s |
| `outcomes(execution)` | The distinct `Outcome`s reached |
| `is_resolved(execution)` | Whether the graph is decided |

### Record and replay

| Name | Description |
|---|---|
| `ExecutionHistory` | A graph, initial answers and ordered answer batches; `from_execution(execution)` starts one |
| `record_execution(history, file_path=None)` | Yield an `ExecutionRecorder`; `record(answers)` appends a batch, `export_history()` returns the history |
| `snapshot(history, step=-1)` | The execution after `step` batches |
| `save_history_file` / `load_history_file` | Save or load a JSON history |
| `viewer.save_history_html(history, path)` | Export an offline replay |

### Agents

| Name | Description |
|---|---|
| `python -m symbolic_reasoning.mcp --srg ID PATH` | Run the MCP server over stdio (`mcp` extra) |
| `symbolic_reasoning.mcp.create_srg_mcp(srgs=...)` | The same server, built in Python |
| `symbolic_reasoning.tools.TOOLS` / `INSTRUCTIONS` | The agent tools and their usage instructions, for any host |
| `symbolic_reasoning.tools.ExecutionStore` | The protocol a host implements to keep executions |
| `symbolic_reasoning.tools.ToolError` | Raised for a call the agent can correct; return its message to the agent |

### Errors

| Name | Raised by |
|---|---|
| `ParseError` | The compilers, for invalid source; has a `loc` |
| `CompilerError` | The compilers, for source that cannot compile; has a `loc` |
| `SRGValidationError` | `load_srg()` and `SRGBuilder.build()`, for an invalid graph |
| `InvalidAnswerError` | `apply_answers()`, for rejected answers |
| `ExecutionNotResolvedError` | `reasoning_trace()` and `outcomes()`, on an unresolved execution |

All are `ValueError`s except `ExecutionNotResolvedError`, a `RuntimeError`.
