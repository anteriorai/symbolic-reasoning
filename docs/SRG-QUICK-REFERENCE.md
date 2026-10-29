# SRG Quick Reference

Syntax and semantics of the `.srg` language. For how policies are evaluated and how to design them, see the [authoring guide](SRG-AUTHORING-GUIDE.md).

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

Arguments are predicates, defines or nested expressions, and are asked in order.

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

## Tooling

`symbolic_reasoning.compiler.parse_srg()` returns the AST and `compile_srg_ast()` compiles one; `@anteriorai/srg-parser` and `@anteriorai/srg-compiler` do the same in TypeScript. Error locations are zero-based lines with UTF-16 columns in both. The formal grammar is [grammar.js](../packages/srg-grammar/grammar.js).
