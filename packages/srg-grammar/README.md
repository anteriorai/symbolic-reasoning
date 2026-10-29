# @anteriorai/srg-grammar

Tree-sitter grammar for the SRG (Symbolic Reasoning Graph) language.

## Installation

```bash
npm install @anteriorai/srg-grammar
```

## Usage

```javascript
// Editor metadata (tokens, comments, brackets, etc.)
import languageConfigJson from '@anteriorai/srg-grammar/language-configuration.json' with { type: 'json' };

console.log(languageConfigJson);
```

## Development

From a clone of the repository:

```bash
npm run generate -w @anteriorai/srg-grammar  # regenerate the parser and wasm (needs Docker)
npm test -w @anteriorai/srg-grammar
npm run parse -w @anteriorai/srg-grammar -- your_file.srg
```

## Grammar

The SRG grammar supports:

- **Predicates**: `predicate id: "question"`
- **Outcomes**: `outcome id: "description"`
- **Aggregators**: `all()`, `any()`, `none()`, `atleast(n, ...)`, etc.
- **Named definitions**: `define name: expression`
- **Paths**: `check => approved` follows true; `check !=> review` follows false.
- **Comments**: `# comment`

See [The SRG language](https://github.com/anteriorai/symbolic-reasoning/blob/master/docs/srg-language.md) for syntax and semantics,
or [grammar.js](https://github.com/anteriorai/symbolic-reasoning/blob/master/packages/srg-grammar/grammar.js) for the complete grammar.
