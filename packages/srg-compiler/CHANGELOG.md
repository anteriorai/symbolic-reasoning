# @anteriorai/srg-compiler

## 0.7.0

### Minor Changes

- ffa81a0: Add `!=>` for false path edges, with parser support. The optional AST
  `Path.conditions` array records one outgoing boolean per step; omission means all true.

  The compiler shares identical path prefixes and named aggregators. Existing source
  and AST inputs remain supported, but generated IDs and node/aggregator counts may change.

- ffa81a0: `metadata` compiles to the symbol's `metadata` field, so it can no longer replace
  fields such as `question` or `name`. A `define` whose body is a single reference
  compiles to its own aggregator, keeping its name, label, doc, citations and
  metadata.
- ffa81a0: Add an optional top-level `policy_context: "..."` declaration to SRG source, with
  regular and triple-quoted strings. Preserve each declaration as a
  PolicyContextDefinition in SourceFile.definitions, including its source location.
  Compile its value into the graph, including through the CLI. Reject duplicate
  declarations during compilation, preserve explicit empty strings, and emit null
  when omitted.

  Remove CompilerOptions and the options parameter from compile, compileFile, and
  compileAST. Declare policy context in the SRG source or AST instead.

### Patch Changes

- ffa81a0: License the packages under Apache-2.0: each package declares `"license": "Apache-2.0"`
  and ships the `LICENSE` file.
- ffa81a0: `compileAST` rejects a definition or expression with an unknown `type`, any key the AST schema does not define (for example `condition` for `conditions`), and a `loc` that is not a location, with a located `CompilerError`, instead of silently dropping or ignoring them.
- ffa81a0: `srg-compile` now defaults to `<input>.json` for any input name and refuses to write over
  the input file, so compiling `policy.txt` or `policy.SRG` no longer replaces the source.
- ffa81a0: Export the parser's error classes, `ParseError`, `SyntaxError`, `StructuralError` and
  `InternalParserError`, so a project that depends on `@anteriorai/srg-compiler` alone, as pnpm
  installs it, can catch the errors `compile` and `compileFile` throw for an invalid policy.
- ffa81a0: A `define` that refers to itself, directly or through other defines, is now a `CompilerError`
  naming the cycle (`'d' refers to itself: d -> e -> d`) at the reference that closes it, instead of
  overflowing the stack.
- ffa81a0: The compiler rejects a second definition of a predicate, outcome or `define` name (they share one
  namespace), a duplicate citation, and definitions named `root`. Names in the schema's
  aggregator and node id formats (`Root`, `A<digits>`, `SN<digits>` and `SN_<digits>`) are
  reserved for graph ids, so a predicate, outcome or `define` can no longer be named `A1` or `SN_2`.
- ffa81a0: Support Node.js 22 and later, and ship tree-sitter's license with the `tree-sitter.wasm` in `@anteriorai/srg-parser`.
- ffa81a0: Undefined reference and undefined outcome errors are now `CompilerError`s carrying the
  location of the misspelled identifier, and duplicate property errors are `StructuralError`s
  at the repeated property, matching the Python compiler.
- ffa81a0: `root` is accepted only as the first step of a path. Anywhere else, including inside an
  aggregator or a `define`, or followed by `!=>`, it is a `CompilerError` at the reference instead
  of a graph with a cycle back to the root or an edge that can never fire.
- ffa81a0: Create a separate graph node for each path-step occurrence while retaining shared
  predicate symbols. This prevents paths that reuse predicates from reaching each
  other's outcomes or forming cycles when steps repeat or appear in opposite orders.
- ffa81a0: `compileFile` and `srg-compile` reject a policy file that is not valid UTF-8 instead of
  replacing its bytes with U+FFFD, matching the Python compiler.
- ffa81a0: Reject a `cite:` that names a citation the policy does not declare, or names the same citation twice, with a `CompilerError` at the reference, instead of compiling a dangling or repeated `citation_ids` entry.
- ffa81a0: `compileAST` rejects a path with no steps, an aggregator with no arguments, a `not` with no expression, and a count that is not a whole number from the strategy's minimum to 2^53 - 1, with a located `CompilerError`, instead of crashing or returning a graph the runtime cannot load.
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
- Updated dependencies [ffa81a0]
  - @anteriorai/srg-parser@0.7.0
  - @anteriorai/srg-types@0.7.0
