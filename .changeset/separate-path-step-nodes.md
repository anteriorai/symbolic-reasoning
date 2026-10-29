---
"@anteriorai/srg-compiler": patch
---

Create a separate graph node for each path-step occurrence while retaining shared
predicate symbols. This prevents paths that reuse predicates from reaching each
other's outcomes or forming cycles when steps repeat or appear in opposite orders.
