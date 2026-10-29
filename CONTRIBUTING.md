# Contributing to symbolic-reasoning

Thank you for your interest in contributing. This document covers how to set up a development environment, run tests, and publish packages.

---

## Repository structure

```
symbolic-reasoning/
├── src/symbolic_reasoning/   # Python runtime library
├── packages/                 # TypeScript packages (types, grammar, parser, compiler)
├── examples/                 # Usage examples
├── tests/                    # Python test suite
├── docs/                     # Documentation
└── schemas/                  # SRG JSON schemas and type generators
```

The TypeScript packages in `packages/` form the `.srg` toolchain and are published separately to npm as `@anteriorai/srg-*`. The Python package in `src/` is published to PyPI as `symbolic-reasoning`.

---

## Development environment

You need [uv](https://docs.astral.sh/uv/) for Python and Node 24 with npm 11 for TypeScript:

```bash
uv sync
npm ci
```

Changing the grammar also needs Docker; see [Grammar](#grammar).

---

## Building

Build all TypeScript packages:

```bash
npm run build
```

To build a specific package:

```bash
npm run build --workspace=packages/srg-compiler
```

---

## Running tests

**TypeScript packages** (builds first, then runs all workspace tests):

```bash
npm run verify
```

**Python runtime:**

```bash
uv run pytest
```

Run a specific test file:

```bash
uv run pytest tests/test_srg_core.py
```

The Python compiler's differential tests compare its output and input validation
with the TypeScript compiler. Build the TypeScript packages first, then enable
these tests explicitly:

```bash
npm run build
SRG_PARITY=1 uv run pytest tests/test_compiler_parity.py
```

They are skipped during Python-only development. CI runs them in a dedicated job
alongside the Python and TypeScript suites. Keep all three passing.

**MCP server tests** skip without the optional `mcp` extra:

```bash
uv sync --all-extras --group dev
uv run pytest tests/mcp --no-cov
```

**Viewer browser tests:** install Chromium, then enable the optional checks:

```bash
uv run --with playwright python -m playwright install chromium
SRG_VIEWER_BROWSER=1 uv run --with playwright pytest --no-cov tests/test_viewer_browser.py
```

Chromium needs its usual system libraries. These tests cover playback, inspection,
traces, and layout. The regular Python suite checks HTML export without a browser.

**Python examples:** run tests in each example's own project environment:

```bash
cd examples/integrations/jev
uv run --locked python -m unittest discover -v
```

Add Python example projects with tests to the `test-examples` matrix in
`.github/workflows/ci.yml`. Each project uses `test_*.py` files discoverable by
`unittest`; default tests run offline without API credentials.

---

## Code style

The runtime graph schema is `schemas/srg-schema-v1.json`; the parser AST contract
is `schemas/srg-ast-v1.json`. Both have generated Python and TypeScript models.
Update the schemas and regenerate instead of editing the generated files:

```bash
uv run python schemas/generate.py
npm run generate
```

The AST types remain available from `@anteriorai/srg-parser`. Their Python counterparts
live in `symbolic_reasoning.gen.py.ast`. Source positions use UTF-16 code units
for columns and offsets, matching web-tree-sitter. CI checks regenerated output.

**Python:** linted with `ruff` and type-checked with `ty`.

```bash
uv run ruff check .
uv run ty check
```

**TypeScript:** follow the conventions in the existing packages.

### Grammar

The tree-sitter parser and WebAssembly module in `packages/srg-grammar` are
generated from `grammar.js` and committed. After changing the grammar, regenerate
them:

```bash
npm run generate -w @anteriorai/srg-grammar
```

This runs Emscripten in the Docker image pinned by `tree-sitter-cli`, so every
machine produces the same bytes. CI checks the committed output.

---

## Tenets

Every change to symbolic-reasoning is held to these:

1. **Solving stays deterministic.** A change must not make an outcome depend on anything but the policy and the answers.
2. **Every outcome explains itself.** A change that loses why a decision was made does not ship.
3. **The policy decides; the oracle only answers facts.** Decision logic belongs in the policy and the runtime, never in what an oracle is expected to infer, and the runtime never assumes an answer the oracle did not give. The core does not know what the oracle is (an LLM, a database or a person), so provider-specific code stays out of it.
4. **Invalid input is rejected at the boundary.** Malformed policies, graphs and answers fail where they enter, with a clear message; a change never guesses what was meant.
5. **One spec binds every implementation.** Change the JSON schemas and regenerate; never edit generated code by hand. A language change lands in the Python and TypeScript compilers together.
6. **Case data never leaks.** Errors and logs never include the answers or case details an execution handles.
7. **Changes prove themselves.** Every behaviour change comes with a test, and every fix or enhancement with a demo a reviewer can judge on its own.
8. **Maintenance cost decides what lands.** Weigh every feature against what it costs to keep alive, and delete code that stops earning its keep.

---

## Code standards

The code standards for Python and TypeScript are in [AGENTS.md](AGENTS.md), which coding agents load automatically. They apply to every change, whoever writes it.

---

## Releasing (Changesets)

The `@anteriorai/srg-*` npm packages and the `symbolic-reasoning` Python package share one version and are released together via Changesets.

1. **Make your change.**
2. **Add a changeset** — run `npm run changeset` and commit the generated `.changeset/*.md` file. A changeset naming any one package bumps them all, Python included, so Python-only changes need one too.
3. **Merge to `master`** — the Release workflow opens a `chore: release vX.Y.Z` PR automatically. That PR runs `npm run version`, which applies the changeset, updates changelogs, and sets the version in `pyproject.toml`, `uv.lock` and `package-lock.json`.
4. **Publish** — merging the release PR publishes the new version to npm and PyPI.

---

## Opening a pull request

- Keep PRs focused. One logical change per PR.
- Add or update tests for any behaviour you change.
- Make sure `npm run verify` and `uv run pytest` both pass locally before opening the PR.
- For changes to the `.srg` language (grammar or compiler), include a fixture in `tests/fixtures/` that exercises the new syntax.
- For a bug fix or an enhancement, include a [before/after demo](#beforeafter-demo).

### Before/after demo

Every bug fix and enhancement PR needs a before/after screenshot or GIF. The test: someone who looks at **only the demo**, not the description or the code, can say what was broken or missing and what the PR changes.

Put these in the demo, in this order:

1. **The input that triggers the bug or the new behaviour.** Show it exactly as the code receives it. If a script changes the input before running, show the changed part, not the original file.
2. **Before (base branch):** what happens, and in plain words what is wrong or missing.
3. **After (your branch):** what happens now with the same input, and why that is right.

#### Example

**The rule:** approve an applicant only if they are **not** on a sanctions list.

```srg
path ok: sanctioned !=> approved    # !=> means "take this arrow when the answer is no"
```

**The bug:** a program can hand the compiler a policy as JSON instead of `.srg` text. In that JSON, the "no" in `!=>` is stored as `"conditions": [false]`. When the key was misspelled `"condition"`, the compiler ignored it without any error. The "no" disappeared, and the rule became "approve an applicant only if they **are** on a sanctions list".

**A good screenshot of the fix:**

```
INPUT
  The rule as JSON, with "conditions" misspelled:
    "condition": [false]
  The applicant: on a sanctions list

BEFORE (master)
  Decision: approved
  ✗ Wrong: the rule says never approve someone on a sanctions list.
    The compiler ignored "condition", so the "no" was lost.

AFTER (this branch)
  CompilerError: Unknown key 'condition' on path
  ✓ The typo now stops the compile instead of flipping the decision.
```
