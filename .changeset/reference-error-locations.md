---
"@anteriorai/srg-compiler": patch
"@anteriorai/srg-parser": patch
---

Undefined reference and undefined outcome errors are now `CompilerError`s carrying the
location of the misspelled identifier, and duplicate property errors are `StructuralError`s
at the repeated property, matching the Python compiler.
