# SRG Authoring Guide

How SRG policies are evaluated, and how to design them, whether you write a `.srg` file by hand or generate one with an LLM. For the syntax, see the [quick reference](SRG-QUICK-REFERENCE.md).

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

A false `support_requested` answer stops this branch; an unknown value takes neither arrow. See the [path reference](SRG-QUICK-REFERENCE.md#paths) for how the compiler shares common prefixes.
