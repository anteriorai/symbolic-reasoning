---
"@anteriorai/srg-compiler": patch
---

Export the parser's error classes, `ParseError`, `SyntaxError`, `StructuralError` and
`InternalParserError`, so a project that depends on `@anteriorai/srg-compiler` alone, as pnpm
installs it, can catch the errors `compile` and `compileFile` throw for an invalid policy.
