# @anteriorai/srg-types

## 0.7.0

### Minor Changes

- ffa81a0: Export `AGGREGATOR_ID_PATTERN` and `NODE_ID_PATTERN`, the aggregator and node id formats from the
  SRG schema.
- ffa81a0: Predicates, outcomes, aggregators and citations hold author metadata in a
  `metadata` field instead of as extra top-level keys, and graph objects no longer
  accept fields outside the schema.

### Patch Changes

- ffa81a0: License the packages under Apache-2.0: each package declares `"license": "Apache-2.0"`
  and ships the `LICENSE` file.
- ffa81a0: Support Node.js 22 and later, and ship tree-sitter's license with the `tree-sitter.wasm` in `@anteriorai/srg-parser`.
- ffa81a0: The graph schema's `item_id` description says only the `Root` node wraps `Root`.
