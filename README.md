> **Research preview.** `symbolic-reasoning` is pre-1.0 and under active development. The API, the `.srg` language and output formats may change between minor releases without deprecation. Review its outputs before relying on them for consequential decisions. Provided "as is", without warranty, under the [Apache 2.0 License](https://github.com/anteriorai/symbolic-reasoning/blob/master/LICENSE).

# symbolic-reasoning

<img src="https://raw.githubusercontent.com/anteriorai/symbolic-reasoning/master/docs/images/symbolic-reasoning.png" width="900" alt="A policy compiles to a symbolic reasoning graph that the solver evaluates. The solver asks an oracle, which draws on case knowledge, and the result is a reasoning trace that leads to an outcome." />

**Make your agents policy-adherent.**

Policies are everywhere: clinical guidelines, insurance coverage criteria, lending rules, compliance checklists. An agent asked to follow one can skip a rule, misapply it, or talk its way to the wrong outcome.

`symbolic-reasoning` takes the logic out of the model. The agent answers questions about the case; the library decides which questions to ask and what the answers add up to, and returns the outcome with a reasoning trace.

Use it two ways:

- **[As agent tools.](https://github.com/anteriorai/symbolic-reasoning#use-with-agents)** Your agent works through the policy with tool calls, over MCP or in any agent framework.
- **[As a workflow.](https://github.com/anteriorai/symbolic-reasoning#quick-start)** Your code drives the solve and an oracle (an LLM, a database, a human) answers each round of questions.

| Concern | Handled by |
|---|---|
| What are the rules? | Your policy (`.srg`) |
| What is true in this case? | Your agent or oracle |
| Which question or decision follows? | The library |
| Why was that decision made? | The reasoning trace |

## Installation

Requires Python 3.12+.

```bash
uv add symbolic-reasoning  # or: pip install symbolic-reasoning
```

## Quick start

Save a policy as `loan_approval.srg`:

```srg
predicate has_good_credit:   "Does the applicant have a credit score of 700 or above?"
predicate has_stable_income: "Does the applicant have stable employment for at least 2 years?"
predicate has_low_dti:       "Is the applicant's debt-to-income ratio below 43%?"
predicate has_down_payment:  "Has the applicant provided at least 20% down payment?"

outcome approved:      "Loan Approved"
outcome denied:        "Loan Denied"
outcome manual_review: "Sent to Manual Review"

define core_eligible: all(has_good_credit, has_stable_income, has_low_dti)

path approve: all(core_eligible, has_down_payment) => approved
path review:  all(core_eligible, not(has_down_payment)) => manual_review
path deny:    not(core_eligible) => denied
```

Solve it with an oracle. This one asks you at the terminal:

```python
import asyncio

import symbolic_reasoning as sr


async def oracle(request: sr.OracleRequest) -> dict[str, sr.Answer]:
    answers = {}
    for predicate_request in request.predicate_requests:
        p = predicate_request.predicate
        reply = input(f"{p.question} (y/n): ")
        answers[p.id] = sr.Answer(is_met=reply == "y", reasoning=f"User answered {reply}")
    return answers


async def main() -> None:
    srg = sr.compile_srg_file("loan_approval.srg")
    execution = await sr.asolve(srg, oracle)

    for path in sr.reasoning_trace(execution).outcome_paths:
        print(srg.outcomes[path.outcome_id].description)
        for step in path.steps:
            mark = "YES" if step.is_met else "NO "
            print(f"  {mark}  {srg.predicates[step.predicate_id].question}")


asyncio.run(main())
```

It prints each outcome reached and the answers that led to it:

```
Sent to Manual Review
  YES  Does the applicant have a credit score of 700 or above?
  YES  Does the applicant have stable employment for at least 2 years?
  YES  Is the applicant's debt-to-income ratio below 43%?
  NO   Has the applicant provided at least 20% down payment?
```

## Learn more

- [The SRG language](https://github.com/anteriorai/symbolic-reasoning/blob/master/docs/srg-language.md): the `.srg` syntax, how policies are evaluated and how to design them.
- [Python guide](https://github.com/anteriorai/symbolic-reasoning/blob/master/docs/python-guide.md): oracles, step-by-step solving, coverage, reasoning traces, recording and replay, and the API reference.

## Use with agents

The quick start runs a policy as a workflow: your code drives the solve and calls the oracle for each round of questions. The agent tools invert that control. The agent drives the solve through tool calls, starting an execution, answering each question from the case evidence and reading the outcomes, while the library still decides which questions are asked and how the answers combine.

Serve the tools over MCP with the `mcp` extra:

```bash
uv add "symbolic-reasoning[mcp]"
uv run python -m symbolic_reasoning.mcp --srg loan_approval loan_approval.srg
```

The server talks over stdio, so a host such as Claude Code launches it. See [MCP setup](https://github.com/anteriorai/symbolic-reasoning/blob/master/docs/mcp.md) to connect one.

To use the tools without MCP, see the [Python guide](https://github.com/anteriorai/symbolic-reasoning/blob/master/docs/python-guide.md#use-with-agents).

## Use with decision models

Every predicate is a yes/no question about the case, which is what a decision model answers. Use one as the oracle: the policy fixes which questions are asked and how their answers combine, and the model answers each from the case evidence. Map its probability to `is_met` and keep the probability in `reasoning`, so the trace shows how confident each answer was.

The [Jev example](https://github.com/anteriorai/symbolic-reasoning/tree/master/examples/integrations/jev) does this with [TypeSafe's Jev](https://docs.typesafe.ai/concepts/system-one).

## Examples

- [`examples/integrations/jev`](https://github.com/anteriorai/symbolic-reasoning/tree/master/examples/integrations/jev): an oracle backed by the Jev decision model, which answers a policy's questions from Markdown case files and records the run.
- [`examples/data`](https://github.com/anteriorai/symbolic-reasoning/tree/master/examples/data): an underwriting policy with an application, and a medical necessity review policy with a synthetic clinical record and a replay.
