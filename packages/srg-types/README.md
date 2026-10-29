# @anteriorai/srg-types

TypeScript type definitions for the SRG (Symbolic Reasoning Graph) schema.

## Installation

```bash
npm install @anteriorai/srg-types
```

## Usage

```typescript
import type { SRG, Predicate, Aggregator, Outcome } from '@anteriorai/srg-types';

// Use the types in your code
function processSRG(srg: SRG) {
  console.log('Predicates:', Object.keys(srg.predicates).length);
  console.log('Aggregators:', Object.keys(srg.aggregators).length);
  console.log('Outcomes:', Object.keys(srg.outcomes).length);
}

// Create an SRG instance
const mySRG: SRG = {
  predicates: {
    is_adult: {
      type: 'Predicate',
      id: 'is_adult',
      question: 'Is the person 18 or older?',
      context: null,
    },
  },
  aggregators: {},
  outcomes: {
    approved: {
      type: 'Outcome',
      id: 'approved',
      description: 'Application approved',
    },
  },
  nodes: {
    Root: { id: 'Root', item_id: 'Root' },
    SN_1: { id: 'SN_1', item_id: 'is_adult' },
    SN_2: { id: 'SN_2', item_id: 'approved' },
  },
  edges: {
    'E_Root->SN_1': { source: 'Root', target: 'SN_1', condition: true },
    'E_SN_1->SN_2': { source: 'SN_1', target: 'SN_2', condition: true },
  },
  policy_context: null,
};
```

## Type Exports

This package exports all types defined in the SRG JSON Schema, including:

- `SRG` - The main SRG structure
- `Predicate` - A predicate (question) definition
- `Aggregator` - An aggregator (boolean logic) definition
- `Outcome` - An outcome definition
- `Node` - A graph node
- `Edge` - A graph edge
- `Strategy` - Aggregation strategies (AllStrategy, AtLeastStrategy, etc.)

## Schema Version

These types are generated from [`schemas/srg-schema-v1.json`](https://github.com/anteriorai/symbolic-reasoning/blob/master/schemas/srg-schema-v1.json).

## Development

This package is part of the [symbolic-reasoning](https://github.com/anteriorai/symbolic-reasoning) monorepo.

These types are automatically generated from the JSON Schema using [`json-schema-to-typescript`](https://github.com/bcherny/json-schema-to-typescript).

