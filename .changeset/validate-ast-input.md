---
"@anteriorai/srg-compiler": patch
---

`compileAST` rejects a path with no steps, an aggregator with no arguments, a `not` with no expression, and a count that is not a whole number from the strategy's minimum to 2^53 - 1, with a located `CompilerError`, instead of crashing or returning a graph the runtime cannot load.
