# @anteriorai/srg-grammar

## 0.7.0

### Minor Changes

- ffa81a0: Add `!=>` for false path edges, with parser support. The optional AST
  `Path.conditions` array records one outgoing boolean per step; omission means all true.

  The compiler shares identical path prefixes and named aggregators. Existing source
  and AST inputs remain supported, but generated IDs and node/aggregator counts may change.

- ffa81a0: Add an optional top-level `policy_context: "..."` declaration to SRG source, with
  regular and triple-quoted strings. Preserve each declaration as a
  PolicyContextDefinition in SourceFile.definitions, including its source location.
  Compile its value into the graph, including through the CLI. Reject duplicate
  declarations during compilation, preserve explicit empty strings, and emit null
  when omitted.

  Remove CompilerOptions and the options parameter from compile, compileFile, and
  compileAST. Declare policy context in the SRG source or AST instead.

### Patch Changes

- ffa81a0: Require nonempty aggregators and integer counts, validate citation regions and
  page numbers, and reject nested syntax
  errors or missing tokens instead of compiling Tree-sitter's recovered input.
- ffa81a0: License the packages under Apache-2.0: each package declares `"license": "Apache-2.0"`
  and ships the `LICENSE` file.
- ffa81a0: Allow comments between a declaration and its properties, and between successive properties, without ending the declaration.
- ffa81a0: End a `#` comment at a carriage return as well as a newline, so a policy saved with
  carriage-return line endings no longer loses every declaration after its first comment.
- ffa81a0: Support Node.js 22 and later, and ship tree-sitter's license with the `tree-sitter.wasm` in `@anteriorai/srg-parser`.
