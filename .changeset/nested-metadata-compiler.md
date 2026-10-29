---
"@anteriorai/srg-compiler": minor
---

`metadata` compiles to the symbol's `metadata` field, so it can no longer replace
fields such as `question` or `name`. A `define` whose body is a single reference
compiles to its own aggregator, keeping its name, label, doc, citations and
metadata.
