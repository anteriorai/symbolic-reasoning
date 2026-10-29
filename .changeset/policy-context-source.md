---
"@anteriorai/srg-grammar": minor
"@anteriorai/srg-parser": minor
"@anteriorai/srg-compiler": minor
---

Add an optional top-level `policy_context: "..."` declaration to SRG source, with
regular and triple-quoted strings. Preserve each declaration as a
PolicyContextDefinition in SourceFile.definitions, including its source location.
Compile its value into the graph, including through the CLI. Reject duplicate
declarations during compilation, preserve explicit empty strings, and emit null
when omitted.

Remove CompilerOptions and the options parameter from compile, compileFile, and
compileAST. Declare policy context in the SRG source or AST instead.
