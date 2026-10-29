# @anteriorai/srg-types

## 0.7.0

### Minor Changes

- c37b963: Export `AGGREGATOR_ID_PATTERN` and `NODE_ID_PATTERN`, the aggregator and node id formats from the
  SRG schema.
- c37b963: Predicates, outcomes, aggregators and citations hold author metadata in a
  `metadata` field instead of as extra top-level keys, and graph objects no longer
  accept fields outside the schema.

### Patch Changes

- c37b963: License the packages under Apache-2.0: each package declares `"license": "Apache-2.0"`
  and ships the `LICENSE` file.
- c37b963: The graph schema's `item_id` description says only the `Root` node wraps `Root`.
