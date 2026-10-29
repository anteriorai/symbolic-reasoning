---
"@anteriorai/srg-compiler": patch
---

`root` is accepted only as the first step of a path. Anywhere else, including inside an
aggregator or a `define`, or followed by `!=>`, it is a `CompilerError` at the reference instead
of a graph with a cycle back to the root or an edge that can never fire.
