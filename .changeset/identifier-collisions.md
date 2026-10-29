---
"@anteriorai/srg-compiler": patch
---

The compiler rejects a second definition of a predicate, outcome or `define` name (they share one
namespace), a duplicate citation, and definitions named `root`. Names in the schema's
aggregator and node id formats (`Root`, `A<digits>`, `SN<digits>` and `SN_<digits>`) are
reserved for graph ids, so a predicate, outcome or `define` can no longer be named `A1` or `SN_2`.
