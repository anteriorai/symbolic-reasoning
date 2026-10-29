# @anteriorai/srg-grammar

Tree-sitter grammar for the SRG (Symbolic Reasoning Graph) language.

## Installation

```bash
npm install @anteriorai/srg-grammar
```

## Usage

```javascript
// Editor metadata (tokens, comments, brackets, etc.)
import languageConfigJson from '@anteriorai/srg-grammar/language-configuration.json';

console.log(languageConfigJson);
```

## Development

### Generate the parser

```bash
npm run build
```

### Run tests

```bash
npm test
```

### Parse a file

```bash
npm run parse your_file.srg
```

## Grammar

The SRG grammar supports:

- **Predicates**: `predicate id: "question"`
- **Outcomes**: `outcome id: "description"`
- **Aggregators**: `all()`, `any()`, `none()`, `atleast(n, ...)`, etc.
- **Named definitions**: `define name: expression`
- **Paths**: `check => approved` follows true; `check !=> review` follows false.
- **Comments**: `# comment`

See the [language reference](../../docs/SRG-QUICK-REFERENCE.md) for syntax and semantics,
or [grammar.js](./grammar.js) for the complete grammar.
