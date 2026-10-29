; Syntax highlighting queries for SRG

; Keywords
[
  "predicate"
  "outcome"
  "define"
  "policy_context"
  "true"
  "false"
] @keyword

; Aggregator functions
[
  "all"
  "any"
  "none"
  "atleast"
  "atmost"
  "exactly"
  "not"
] @function.builtin

; Operators
["=>" "!=>"] @operator
":" @punctuation.delimiter
"," @punctuation.delimiter

; Brackets
["(" ")" "[" "]" "{" "}"] @punctuation.bracket

; Component definitions - these get special colors when being defined
(predicate_definition id: (identifier) @function)
(outcome_definition id: (identifier) @type)
(aggregator_definition id: (identifier) @variable.parameter)

; Component references - references to predicates/aggregators
(reference (identifier) @variable)

; Outcome references (right side of =>)
(path outcome: (identifier) @type)

; Property keys in property blocks
(property key: (identifier) @property)

; Booleans
(boolean) @boolean

; Numbers
(number) @number

; Strings
(string) @string

; Escape sequences
(escape_sequence) @string.escape

; Comments
(comment) @comment
