---
"@anteriorai/srg-compiler": patch
---

Reject a `cite:` that names a citation the policy does not declare, or names the same citation twice, with a `CompilerError` at the reference, instead of compiling a dangling or repeated `citation_ids` entry.
