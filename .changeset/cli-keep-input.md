---
"@anteriorai/srg-compiler": patch
---

`srg-compile` now defaults to `<input>.json` for any input name and refuses to write over
the input file, so compiling `policy.txt` or `policy.SRG` no longer replaces the source.
