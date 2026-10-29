# The SRG Language

The syntax of `.srg` policies, how they are evaluated, and how to design them, whether you write a policy by hand or generate one with an LLM.

## Declarations

```srg
# Comments start with #
policy_context: "<guidance for the whole policy>"
predicate <id>: "<question>"
outcome <id>: "<description>"
define <id>: <expression>
citation <id>: { ... }
path <id>: <expression> => <outcome>
```

Declarations can appear in any order; a name can be referenced before it is declared. Whitespace and indentation are not significant.

## Policy context

```srg
policy_context: """
Evaluate eligibility under the 2026 underwriting policy.
Use the applicant's circumstances at the application date.
"""
```

Optional, and at most once. It becomes the graph's `policy_context` and is passed to the oracle with every request. Without it, `policy_context` is `null`.

## Predicates, outcomes and defines

```srg
predicate is_adult: "Is the patient 18 or older?"
  label:    "Adult"
  context:  "Check the date of birth."
  cite:     policy_doc
  metadata: { priority: 1 }

outcome approved: "Request approved"
  label: "Approved"
  cite:  [policy_doc, appendix]

define basic_check: all(is_adult, has_insurance)
  label: "Basic check"
  doc:   "Combines the basic requirements."
```

A `define` names an expression so several paths can share it.

## Citations

```srg
citation policy_doc: {
  source_ref: "policy.pdf"
  filename:   "policy.pdf"
  regions:    [{ page: 5, box: [[0.1, 0.2], [0.9, 0.2], [0.9, 0.4], [0.1, 0.4]] }]
  excerpt:    "Applicants must be 18 or older."
}
```

`source_ref` is required. Each region has a zero-based `page` and a `box` of four `[x, y]` vertices. Any other key, such as `jurisdiction: "EU"`, becomes the citation's `metadata`. Cite a citation from a predicate, outcome, define or path with `cite: id` or `cite: [id, ...]`.

## Paths

```srg
path approve:  all(is_adult, has_insurance) => approved
path chained:  basic_check => clinical_review => approved
path fallback: home_plan !=> facility_plan => approved
```

`=>` continues when the preceding step is true and `!=>` when it is false; an unanswered step takes neither. The last step leads to an outcome. A path may start with `root =>`, which is implied otherwise; `root` is valid nowhere else.

Paths that start with the same steps share those graph nodes, and identical paths are merged. Refer to predicates and outcomes by their IDs, not by generated node IDs.

## Expressions

```srg
all(a, b, c)          # all true
any(a, b, c)          # at least one true
none(a, b, c)         # all false
not(a)                # false
atleast(2, a, b, c)   # at least 2 true
atmost(1, a, b, c)    # at most 1 true
exactly(2, a, b, c)   # exactly 2 true
```

Arguments are predicates, defines or nested expressions, and are asked in order; see [How questions are asked](#how-questions-are-asked).

## Properties

| Property   | Value                 | Allowed on |
|------------|-----------------------|------------|
| `label`    | string                | predicates, outcomes, defines, paths |
| `doc`      | string                | predicates, outcomes, defines, paths |
| `cite`     | id or `[id, ...]`     | predicates, outcomes, defines, paths |
| `metadata` | `{ key: value, ... }` | predicates, outcomes, defines, paths |
| `context`  | string                | predicates |

Each property may appear once per declaration. None of them affect evaluation. `context` is guidance for the oracle. The others are compiled onto the predicate, outcome or define (`metadata` under its `metadata` field) and also reach the oracle with each predicate, so keep anything the answering model should not see out of the policy. Annotations on a path stay in the source.

## Values

```srg
"string with \n escapes"
"""multi-line
string"""
42
3.14
true
false
[1, "a", true]
{ key: "value", nested: { a: 1 } }
```

Arrays and objects are allowed in `metadata` and citations, and trailing commas are allowed in both. Object keys are identifiers. Negative numbers, exponents and `null` are not supported.

## Identifiers

- Start with a letter or `_`, then letters, digits or `_`.
- Predicates, outcomes and defines share one namespace; citations have their own.
- Reserved: `root`, the graph IDs `Root`, `A<digits>`, `SN<digits>` and `SN_<digits>`, and the operators `all`, `any`, `none`, `not`, `atleast`, `atmost`, `exactly`.
- Declaration and property keywords (`predicate`, `label`, `metadata` and so on) are valid identifiers.

## How questions are asked

An SRG is evaluated by asking questions until the answers determine an outcome.

### Questions are skipped once an expression is decided

Within an expression, the remaining arguments are not asked once its result is known:

- `all(...)`: once any condition is false.
- `any(...)` and `none(...)`: once any condition is true.
- `atleast(N, ...)`, `atmost(N, ...)` and `exactly(N, ...)`: once the count is determined.

This avoids unnecessary, expensive or sensitive questions, but you cannot assume every question in an expression will be asked. To answer every requirement, for example to list all the reasons behind a denial, solve with `Coverage.REACHABLE`, which answers every predicate on the branches the graph reaches.

Short-circuiting is per expression. A predicate that appears in two branches can still be asked for one branch after the other has decided an outcome.

### Order determines which questions are asked

Given `all(A, B, C)`, A is asked first. If A is false, B and C are never asked. Put the most decisive questions first, such as a basic eligibility check, so later questions are asked only when they matter.

## Designing outcomes

### Multiple outcomes can be reached at once

An SRG has no priority or conflict resolution between outcomes. If two paths' conditions are met, both outcomes are reached. Whether outcomes are mutually exclusive is up to how you write the paths.

### Handling contradictory outcomes

If two outcomes should never both apply, such as `approved` and `denied`, there are two reliable approaches.

**Model only one side.** Define paths only for `approved`, and treat reaching no outcome as denial. Contradiction is impossible by construction.

```srg
outcome approved: "Loan Approved"

path approve: all(has_good_credit, has_stable_income) => approved
```

**Write mutually exclusive paths.** Define paths for both outcomes, with conditions that cannot both be true:

```srg
outcome approved: "Loan Approved"
outcome denied:   "Loan Denied"

path approve: all(has_good_credit, has_stable_income) => approved
path deny:    not(all(has_good_credit, has_stable_income)) => denied
```

Overlapping conditions on contradictory outcomes are the most common mistake in policy construction.

### When no outcome is reached

A policy can reach no outcome for a set of answers, for example when it only covers certain cases. This is not an error but a gap in the policy, so handle it explicitly in your application.

## Patterns

### Exclude disqualifying conditions

```srg
define safe_to_proceed: all(
  basic_eligible,
  none(contraindication_a, contraindication_b)
)
```

### Staged evaluation

Chain steps when a decision should pass through gates in sequence; later gates open only if earlier ones pass:

```srg
path full_approval: basic_check => clinical_review => final_approval => approved
```

### Fallback after a failed check

Use `!=>` to continue when the preceding check is false. For example, try a facility plan only after the home plan fails:

```srg
path home_approved: support_requested => home_criteria => approved
path facility_approved: support_requested => home_criteria !=> facility_criteria => approved
path support_review: support_requested => home_criteria !=> facility_criteria !=> needs_review
```

A false `support_requested` answer stops this branch; an unknown value takes neither arrow. The three paths share their common first steps, as described under [Paths](#paths).

## Tooling

`symbolic_reasoning.compiler.parse_srg()` returns the AST and `compile_srg_ast()` compiles one; `@anteriorai/srg-parser` and `@anteriorai/srg-compiler` do the same in TypeScript. Error locations are zero-based lines with UTF-16 columns in both. The formal grammar is [grammar.js](../packages/srg-grammar/grammar.js).
