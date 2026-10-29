---
"@anteriorai/srg-compiler": patch
---

A `define` that refers to itself, directly or through other defines, is now a `CompilerError`
naming the cycle (`'d' refers to itself: d -> e -> d`) at the reference that closes it, instead of
overflowing the stack.
