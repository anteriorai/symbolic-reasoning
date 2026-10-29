---
"@anteriorai/srg-compiler": patch
---

`compileFile` and `srg-compile` reject a policy file that is not valid UTF-8 instead of
replacing its bytes with U+FFFD, matching the Python compiler.
