---
"@anteriorai/srg-compiler": patch
---

`compileAST` rejects a definition or expression with an unknown `type`, any key the AST schema does not define (for example `condition` for `conditions`), and a `loc` that is not a location, with a located `CompilerError`, instead of silently dropping or ignoring them.
