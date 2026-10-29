# @anteriorai/srg-parser

Parser for the SRG (Symbolic Reasoning Graph) language. Converts `.srg` source files to Abstract Syntax Trees (AST).

## Installation

```bash
npm install @anteriorai/srg-parser
```

## Usage

```typescript
import { parse } from '@anteriorai/srg-parser';

const source = `
predicate is_adult: "Is patient 18 or older?"
outcome approved: "Approved"
path approve: is_adult => approved
`;

const ast = await parse(source);
```

## Bundler Configuration (Vite)

This package uses WASM. If you are using Vite, you may need to exclude it from dependency optimization to ensure WASM assets are loaded correctly in development mode:

```javascript
// vite.config.js
export default defineConfig({
  optimizeDeps: {
    exclude: ['@anteriorai/srg-parser']
  }
});
```

## API

### `parse(source: string): Promise<SourceFile>`

Parses SRG source code and returns a typed AST with location information.

### Types

All AST types are exported for TypeScript usage:

```typescript
import type { 
  Position,
  Location,
  SourceFile,
  PredicateDefinition,
  OutcomeDefinition,
  AggregatorDefinition,
  Path,
  Expression
} from '@anteriorai/srg-parser';
```
