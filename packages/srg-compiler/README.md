# @anteriorai/srg-compiler

Compiles `.srg` policies to the graph JSON that the Python `symbolic_reasoning` runtime loads.

## Installation

```bash
npm install @anteriorai/srg-compiler
```

## Usage

```typescript
import { compile, compileFile } from '@anteriorai/srg-compiler';

const graph = await compile(`
predicate is_adult: "Is the patient 18 or older?"
outcome approved: "Approved"
path approve: is_adult => approved
`);

const fromFile = await compileFile('policy.srg');
```

`compileAST` compiles an AST from `parse`. Invalid source throws a `ParseError` (`SyntaxError` or `StructuralError`), and source that cannot compile throws a `CompilerError`, each with a zero-based `loc`. An `InternalParserError` is a parser bug, not a policy error. All of these are exported from this package.

### CLI

The package installs an `srg-compile` command:

```bash
npx srg-compile policy.srg                      # writes policy.srg.json
npx srg-compile policy.srg --output graph.json
npx srg-compile policy.srg --pretty
```

Run it where the package is installed. Elsewhere, name the package explicitly: `npx -p @anteriorai/srg-compiler srg-compile policy.srg`.

## Output

The output matches [`schemas/srg-schema-v1.json`](https://github.com/anteriorai/symbolic-reasoning/blob/master/schemas/srg-schema-v1.json) and the `@anteriorai/srg-types` types. Load it in Python with `symbolic_reasoning.load_srg(json_text)`.
