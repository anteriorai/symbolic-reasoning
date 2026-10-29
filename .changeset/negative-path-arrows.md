---
"@anteriorai/srg-grammar": minor
"@anteriorai/srg-parser": minor
"@anteriorai/srg-compiler": minor
---

Add `!=>` for false path edges, with parser support. The optional AST
`Path.conditions` array records one outgoing boolean per step; omission means all true.

The compiler shares identical path prefixes and named aggregators. Existing source
and AST inputs remain supported, but generated IDs and node/aggregator counts may change.
