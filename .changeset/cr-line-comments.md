---
"@anteriorai/srg-grammar": patch
"@anteriorai/srg-parser": patch
---

End a `#` comment at a carriage return as well as a newline, so a policy saved with
carriage-return line endings no longer loses every declaration after its first comment.
