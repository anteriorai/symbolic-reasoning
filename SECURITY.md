# Security policy

## Supported versions

| Version            | Supported          |
| ------------------ | ------------------ |
| Latest 0.x release | :white_check_mark: |
| Earlier releases   | :x:                |

`symbolic-reasoning` is pre-1.0, so only the latest release receives security fixes. Since 0.7.0, the PyPI package and the `@anteriorai/srg-*` npm packages release together under one version number. Upgrade to the latest release before you report.

## Reporting a vulnerability

**Do not report security vulnerabilities in public issues, pull requests or any other public channel.**

Use GitHub's [private vulnerability reporting](https://github.com/anteriorai/symbolic-reasoning/security/advisories/new) instead. The report stays private until the maintainers publish an advisory.

Include:

- what the vulnerability is and what an attacker gains from it
- the affected package and version: `symbolic-reasoning` on PyPI, or `@anteriorai/srg-types`, `@anteriorai/srg-grammar`, `@anteriorai/srg-parser` or `@anteriorai/srg-compiler` on npm
- the smallest input that reproduces it, such as a `.srg` policy, a compiled SRG loaded with `load_srg`, a recording loaded with `load_history_file`, or a sequence of MCP tool calls
- a suggested fix, if you have one

Never put real patient records, personal data or other confidential case material in a report. Reproduce the problem with synthetic data like the records in [`examples/data`](examples/data).

## What to expect

- **Acknowledgement** within 72 hours of your report
- **Status update** within 7 days with an initial assessment
- **Resolution target** of 30 days for confirmed vulnerabilities, sooner for critical ones

If we accept the report, we fix it, agree a disclosure date with you, publish a GitHub security advisory and credit you in it and in the release notes, unless you prefer to stay anonymous. If we decline it, we explain why.

## Scope

This policy covers what we publish from this repository:

- the `symbolic-reasoning` Python package, including the compiler, solver, recording and replay, agent tools, MCP server (`symbolic_reasoning.mcp`) and HTML viewer (`symbolic_reasoning.viewer`) with its vendored copy of dagre
- the `@anteriorai/srg-*` npm packages, including the grammar compiled to WebAssembly and the tree-sitter runtime bundled with `@anteriorai/srg-parser`
- the workflows in `.github/workflows` that build and publish them

The runtime decides which questions to ask and how the answers combine. It does not check that an answer is true, and it makes no network calls of its own. Your oracle decides where case data goes.

Reports we want:

- a viewer page that runs script or loads remote content when it renders text from a policy, an answer or a recording. Oracle reasoning often quotes case evidence, so the viewer treats all of it as untrusted.
- a crafted policy, compiled SRG, recording or MCP tool call that crashes the parser, compiler or solver outside its documented errors, hangs it, or makes it use memory far out of proportion to the input
- an MCP tool call that reads or changes anything beyond the policies the server was started with and the executions it holds
- crafted input that makes an outcome or reasoning trace disagree with the policy and the answers given. The trace is the audit record of a decision, so a wrong one is a security bug.
- a compromise of the release pipeline, or a published package that differs from what the release workflow builds from this repository

Out of scope:

- wrong answers from your oracle, including an LLM oracle misled by prompt injection in the case evidence. The runtime takes the oracle's answers as given.
- a policy that reaches the wrong outcome because its rules are wrong. That is a policy bug; open a regular issue.
- the MCP host and the model behind it. The server talks over stdio and trusts the host that launched it.
- the projects under `examples/`, which we do not publish
- vulnerabilities in third-party dependencies, unless the way this project uses one makes it exploitable. Report those upstream; Dependabot tracks them here.

## Security measures in this project

- **Dependency scanning.** Dependabot alerts and Dependabot security updates are on.
- **Secret scanning.** GitHub secret scanning is on, including non-provider patterns, AI detection and validity checks.
- **Push protection.** Secret scanning push protection blocks pushes that contain supported secrets, unless the pusher bypasses the block with a reason.
- **Code scanning.** CodeQL default setup analyses the Python, JavaScript/TypeScript and GitHub Actions code on pull requests to `master`, on pushes to `master` and weekly, and reports findings to the Security tab.
- **Pinned actions.** Every action in the CI and release workflows is pinned to a full Git SHA instead of a movable tag, and the CI workflow's token is read-only.
- **Locked dependencies.** The `Lockfile consistency` check fails if `uv.lock` is not canonical or `package-lock.json` does not match `package.json`.
- **Checked generated code.** The `Check Generated Files` check regenerates the Python and TypeScript types, the tree-sitter C parser and `tree-sitter-srg.wasm` from their sources, and fails if the committed files differ.
- **Trusted publishing.** Releases publish from GitHub Actions through OIDC, and the release workflow uses no registry tokens. npm releases from 0.7.0 on carry SLSA provenance attestations.
- **Private vulnerability reporting.** On, so you can report through the Security tab as described above.
- **Branch protection.** Rulesets on `master` require changes to arrive by pull request with every CI check green, and block force pushes and branch deletion.

## Preferred languages

We accept security reports in English.
