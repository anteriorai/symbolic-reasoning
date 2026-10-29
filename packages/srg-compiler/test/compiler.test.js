/**
 * Tests for the SRG compiler
 * Uses Node.js built-in test runner
 */

import { after, before, describe, it } from 'node:test';
import assert from 'node:assert';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { parse, compileAST as compile, compile as compileSource, compileFile, CompilerError } from '../dist/index.js';
import * as srgCompiler from '../dist/index.js';
import { AST_KEYS, NESTED_KEYS } from '../dist/compiler.js';

// Compare complete graph paths, independent of generated node IDs, and fail
// explicitly if sharing a step has introduced a cycle.
function graphPaths(srg, nodeId = 'Root', ancestors = []) {
  assert.ok(!ancestors.includes(nodeId), `Cycle through node ${nodeId}`);
  const itemId = srg.nodes[nodeId].item_id;
  const edges = Object.values(srg.edges).filter(edge => edge.source === nodeId);
  if (edges.length === 0) return [[itemId]];
  return edges.flatMap(edge => {
    assert.strictEqual(edge.condition, true);
    return graphPaths(srg, edge.target, [...ancestors, nodeId])
      .map(path => [itemId, ...path]);
  });
}

describe('SRG Compiler', () => {
  describe('Basic Compilation', () => {
    it('should compile a simple predicate and outcome', async () => {
      const source = `
predicate is_adult: "Is patient over 18?"
outcome approved: "Approved"
path p1: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.predicates.is_adult);
      assert.strictEqual(srg.predicates.is_adult.question, 'Is patient over 18?');
      assert.ok(srg.outcomes.approved);
      assert.strictEqual(srg.outcomes.approved.description, 'Approved');
    });

    it('should only create nodes for items used in paths', async () => {
      const source = `
predicate p1: "Test"
predicate p2: "Unused"
outcome o1: "Result"
outcome o2: "Unused"
path path1: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have Root node + aggregator node + outcome node = 3 nodes
      const nodeCount = Object.keys(srg.nodes).length;
      assert.strictEqual(nodeCount, 3, 'Should have Root, aggregator, and outcome nodes only');
      
      const nodeItems = Object.values(srg.nodes).map(n => n.item_id);
      
      // Should have outcome o1 (used in path)
      assert.ok(nodeItems.includes('o1'), 'Should have node for outcome o1');
      
      // Should have aggregator for all(p1)
      const hasAggregator = nodeItems.some(id => id.startsWith('A'));
      assert.ok(hasAggregator, 'Should have node for aggregator');
      
      // Should NOT have nodes for unused predicate or outcome
      assert.ok(!nodeItems.includes('p1'), 'Should NOT have node for predicate p1 (only aggregator references it)');
      assert.ok(!nodeItems.includes('p2'), 'Should NOT have node for unused predicate p2');
      assert.ok(!nodeItems.includes('o2'), 'Should NOT have node for unused outcome o2');
    });

    it('should create edges between nodes', async () => {
      const source = `
predicate p1: "Test"
outcome o1: "Result"
path path1: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(Object.keys(srg.edges).length > 0);
    });
  });

  describe('Aggregator Generation', () => {
    it('should create aggregators for all() expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path path1: all(p1, p2) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(Object.keys(srg.aggregators).length > 0);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'AllStrategy');
      assert.strictEqual(agg.truth_value, true);
      assert.ok(agg.argument_ids.includes('p1'));
      assert.ok(agg.argument_ids.includes('p2'));
    });

    it('should create aggregators for any() expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path path1: any(p1, p2) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'AtLeastStrategy');
      assert.strictEqual(agg.strategy.count, 1);
      assert.strictEqual(agg.truth_value, true);
    });

    it('should create aggregators for none() expressions', async () => {
      const source = `
predicate p1: "condition 1"
outcome o1: "Result"
path p: none(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'AllStrategy');
      assert.strictEqual(agg.truth_value, false);
    });

    it('should create aggregators for not() expressions', async () => {
      const source = `
predicate p1: "condition 1"
outcome o1: "Result"
path p: not(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'AllStrategy');
      assert.strictEqual(agg.truth_value, false);
    });

    it('should create aggregators for atleast() expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
predicate p3: "condition 3"
outcome o1: "Result"
path p: atleast(2, p1, p2, p3) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'AtLeastStrategy');
      assert.strictEqual(agg.strategy.count, 2);
      assert.strictEqual(agg.truth_value, true);
    });

    it('should create aggregators for atmost() expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path p: atmost(1, p1, p2) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'AtMostStrategy');
      assert.strictEqual(agg.strategy.count, 1);
      assert.strictEqual(agg.truth_value, true);
    });

    it('should create aggregators for exactly() expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path p: exactly(1, p1, p2) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.strategy.type, 'ExactlyStrategy');
      assert.strictEqual(agg.strategy.count, 1);
      assert.strictEqual(agg.truth_value, true);
    });

    it('should generate aggregator IDs starting with A', async () => {
      const source = `
predicate p1: "Test"
outcome o1: "Result"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const aggIds = Object.keys(srg.aggregators);
      assert.ok(aggIds.length > 0);
      assert.ok(/^A\d+$/.test(aggIds[0]), `Aggregator ID should match pattern A\\d+, got ${aggIds[0]}`);
    });
  });

  describe('Named Aggregators', () => {
    it('should handle named aggregators', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
define is_eligible: all(p1, p2)
path p: is_eligible => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators)[0];
      assert.strictEqual(agg.name, 'is_eligible');
    });

    it('should preserve aggregator names in nested expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
predicate p3: "condition 3"
outcome o1: "Result"
define group1: all(p1, p2)
path p: all(group1, p3) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Find the named aggregator
      const namedAgg = Object.values(srg.aggregators).find(a => a.name === 'group1');
      assert.ok(namedAgg, 'Should have named aggregator group1');
      assert.ok(namedAgg.argument_ids.includes('p1'));
      assert.ok(namedAgg.argument_ids.includes('p2'));
    });
  });

  describe('Multiple Paths', () => {
    it('should handle multiple paths to different outcomes', async () => {
      const source = `
predicate p1: "condition 1"
outcome o1: "Approved"
outcome o2: "Denied"
path p: all(p1) => o1
path p: not(p1) => o2
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.strictEqual(Object.keys(srg.outcomes).length, 2);
      assert.ok(srg.outcomes.o1);
      assert.ok(srg.outcomes.o2);
    });

    it('should create multiple aggregators for complex logic', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
predicate p3: "condition 3"
outcome o1: "Result 1"
outcome o2: "Result 2"
path p: all(p1, p2) => o1
path p: any(p2, p3) => o2
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(Object.keys(srg.aggregators).length >= 2);
    });
  });

  describe('Path Isolation', () => {
    it('should not splice paths through a shared predicate', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
outcome y: "Y"
path one: a => b => x
path two: c => b => y
`;
      const ast = await parse(source);
      const srg = compile(ast);

      assert.deepStrictEqual(graphPaths(srg).sort(), [
        ['Root', 'a', 'b', 'x'],
        ['Root', 'c', 'b', 'y'],
      ]);
      assert.deepStrictEqual(Object.keys(srg.predicates).sort(), ['a', 'b', 'c']);
    });

    it('should preserve separate paths through a define of one predicate', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
outcome y: "Y"
define shared: b
path one: a => shared => x
path two: c => shared => y
`;
      const ast = await parse(source);
      const srg = compile(ast);
      const shared = Object.values(srg.aggregators).find(agg => agg.name === 'shared');

      assert.deepStrictEqual(shared.argument_ids, ['b']);
      assert.deepStrictEqual(graphPaths(srg).sort(), [
        ['Root', 'a', shared.id, 'x'],
        ['Root', 'c', shared.id, 'y'],
      ]);
    });

    it('should preserve a shared step at different path positions', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path one: a => b => x
path two: b => y
`;
      const ast = await parse(source);
      const srg = compile(ast);

      assert.deepStrictEqual(graphPaths(srg).sort(), [
        ['Root', 'a', 'b', 'x'],
        ['Root', 'b', 'y'],
      ]);
    });

    it('should preserve steps in opposite orders without creating a cycle', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path one: a => b => x
path two: b => a => y
`;
      const ast = await parse(source);
      const srg = compile(ast);

      assert.deepStrictEqual(graphPaths(srg).sort(), [
        ['Root', 'a', 'b', 'x'],
        ['Root', 'b', 'a', 'y'],
      ]);
    });

    it('should preserve repeated steps without creating a self-loop', async () => {
      const source = `
predicate a: "A"
outcome x: "X"
path one: a => a => x
`;
      const ast = await parse(source);
      const srg = compile(ast);

      assert.deepStrictEqual(graphPaths(srg), [['Root', 'a', 'a', 'x']]);
    });

    it('should preserve separate paths through named aggregators', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
outcome y: "Y"
define shared: all(b)
path one: a => shared => x
path two: c => shared => y
`;
      const ast = await parse(source);
      const srg = compile(ast);
      const paths = graphPaths(srg).map(path => path.map(itemId =>
        srg.aggregators[itemId]?.name || itemId
      ));

      assert.deepStrictEqual(paths.sort(), [
        ['Root', 'a', 'shared', 'x'],
        ['Root', 'c', 'shared', 'y'],
      ]);
    });

    it('should preserve separate paths through inline aggregators', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
outcome y: "Y"
path one: a => all(b) => x
path two: c => all(b) => y
`;
      const ast = await parse(source);
      const srg = compile(ast);
      const paths = graphPaths(srg).map(path => path.map(itemId => {
        const aggregator = srg.aggregators[itemId];
        if (!aggregator) return itemId;
        assert.deepStrictEqual(aggregator.strategy, { type: 'AllStrategy' });
        assert.deepStrictEqual(aggregator.argument_ids, ['b']);
        return 'all(b)';
      }));

      assert.deepStrictEqual(paths.sort(), [
        ['Root', 'a', 'all(b)', 'x'],
        ['Root', 'c', 'all(b)', 'y'],
      ]);
    });

    it('should keep one root and one terminal node per shared outcome', async () => {
      const source = `
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
path one: root => a => b => x
path two: root => c => b => x
`;
      const ast = await parse(source);
      const srg = compile(ast);
      assert.deepStrictEqual(graphPaths(srg).sort(), [
        ['Root', 'a', 'b', 'x'],
        ['Root', 'c', 'b', 'x'],
      ]);
      assert.strictEqual(Object.values(srg.nodes).filter(n => n.item_id === 'Root').length, 1);
      assert.strictEqual(Object.values(srg.nodes).filter(n => n.item_id === 'x').length, 1);
    });
  });

  describe('Property Handling', () => {
    it('should handle predicate context property', async () => {
      const source = `
predicate p1: "Is patient eligible?"
  context: "Check age and insurance"
outcome o1: "Approved"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.strictEqual(srg.predicates.p1.context, 'Check age and insurance');
    });

    it('should handle custom properties on predicates', async () => {
      const source = `
predicate p1: "Test"
  metadata: {
    policy_ref: "Policy v2.1",
    priority: 1,
    enabled: true
  }
outcome o1: "Result"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.deepStrictEqual(srg.predicates.p1.metadata, {
        policy_ref: 'Policy v2.1',
        priority: 1,
        enabled: true,
      });
    });

    it('should handle nested object properties', async () => {
      const source = `
predicate p1: "Test"
  metadata: {
    policy_ref: {
      text: "Policy text",
      page: 42
    }
  }
outcome o1: "Result"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const { policy_ref } = srg.predicates.p1.metadata;
      assert.strictEqual(policy_ref.text, 'Policy text');
      assert.strictEqual(policy_ref.page, 42);
    });

    it('should handle array properties', async () => {
      const source = `
predicate p1: "Test"
  metadata: {
    tags: ["eligibility", "age", "critical"]
  }
outcome o1: "Result"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.deepStrictEqual(srg.predicates.p1.metadata.tags, ["eligibility", "age", "critical"]);
    });

    it('should handle properties on outcomes', async () => {
      const source = `
predicate p1: "Test"
outcome o1: "Result"
  metadata: {
    notification_required: true,
    level: 2
  }
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.strictEqual(srg.outcomes.o1.metadata.notification_required, true);
      assert.strictEqual(srg.outcomes.o1.metadata.level, 2);
    });

    it('should handle properties on aggregators', async () => {
      const source = `
predicate p1: "Test"
predicate p2: "Test 2"
outcome o1: "Result"
define check: all(p1, p2)
  doc: "Combined check"
  metadata: {
    version: 2
  }
path p: check => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const namedAgg = Object.values(srg.aggregators).find(a => a.name === 'check');
      assert.ok(namedAgg);
      assert.strictEqual(namedAgg.doc, 'Combined check');
      assert.strictEqual(namedAgg.metadata.version, 2);
    });

    it('should compile policy context from source', async () => {
      const source = `
policy_context: "Test Policy v1.0"
predicate p1: "Test"
outcome o1: "Result"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.strictEqual(srg.policy_context, 'Test Policy v1.0');
    });
  });

  describe('Schema Validation', () => {
    it('should produce output that matches the schema', async () => {
      const source = `
predicate p1: "Test predicate"
outcome o1: "Test outcome"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Check required fields
      assert.ok(srg.predicates);
      assert.ok(srg.aggregators);
      assert.ok(srg.outcomes);
      assert.ok(srg.nodes);
      assert.ok(srg.edges);
      
      // Check predicate structure
      assert.strictEqual(srg.predicates.p1.type, 'Predicate');
      assert.strictEqual(srg.predicates.p1.id, 'p1');
      assert.ok(srg.predicates.p1.question);
      
      // Check outcome structure
      assert.strictEqual(srg.outcomes.o1.type, 'Outcome');
      assert.strictEqual(srg.outcomes.o1.id, 'o1');
      assert.ok(srg.outcomes.o1.description);
    });

    it('should validate against Zod schema without errors', async () => {
      const source = `
predicate p1: "Test"
predicate p2: "Test 2"
outcome o1: "Result"
path p: all(p1, p2) => o1
`;
      
      const ast = await parse(source);
      
      // This should not throw due to validation in compile()
      assert.doesNotThrow(() => compile(ast));
    });
  });

  describe('Error Handling', () => {
    it('should throw error for undefined predicate reference', async () => {
      const source = `
outcome o1: "Result"
path p: all(P_UNDEFINED) => o1
`;
      
      const ast = await parse(source);
      
      assert.throws(() => compile(ast));
    });

    it('should throw error for undefined outcome reference', async () => {
      const source = `
predicate p1: "Test"
outcome o1: "Result"
path p: all(p1) => O_UNDEFINED
`;
      
      const ast = await parse(source);
      
      assert.throws(() => compile(ast));
    });

    it('should throw error for undefined named aggregator', async () => {
      const source = `
predicate p1: "Test"
outcome o1: "Result"
path p: undefined_aggregator => o1
`;
      
      const ast = await parse(source);
      
      assert.throws(() => compile(ast));
    });
  });

  describe('Nested Expressions', () => {
    it('should handle deeply nested aggregators', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
predicate p3: "condition 3"
outcome o1: "Result"
path p: all(p1, any(p2, p3)) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have multiple aggregators (one for all, one for any)
      assert.ok(Object.keys(srg.aggregators).length >= 2);
    });

    it('should handle negation of nested expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path p: not(all(p1, p2)) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have aggregators for both not() and all()
      assert.ok(Object.keys(srg.aggregators).length >= 2);
    });

    it('should preserve empty policy context and use null when omitted', async () => {
      assert.strictEqual(compile(await parse('policy_context: ""')).policy_context, '');
      assert.strictEqual(compile(await parse('')).policy_context, null);
    });

    it('should reject duplicate context during compilation with its source location', async () => {
      const source = 'policy_context: ""\npolicy_context: "second"';
      const ast = await parse(source);
      assert.strictEqual(ast.definitions.length, 2);
      const isDuplicate = error => error instanceof CompilerError &&
        /Duplicate policy_context/.test(error.message) && error.loc.start.line === 1;
      assert.throws(() => compile(ast), isDuplicate);
      await assert.rejects(() => compileSource(source), isDuplicate);
    });

    it('should validate context definitions supplied directly in an AST', () => {
      const loc = {
        start: { line: 0, column: 0, offset: 0 },
        end: { line: 0, column: 18, offset: 18 },
      };
      const context = { type: 'policy_context_definition', value: '', loc };
      const ast = { type: 'source_file', definitions: [context] };
      assert.strictEqual(compile(ast).policy_context, '');
      assert.throws(
        () => compile({ ...ast, definitions: [context, { ...context, value: 'second' }] }),
        /Duplicate policy_context/,
      );
    });

  });

  describe('Chained Paths', () => {
    it('should handle explicit root with chained expressions', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path p: root => all(p1) => any(p2) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have Root node
      assert.ok(srg.nodes.Root);
      assert.strictEqual(srg.nodes.Root.id, 'Root');
      
      // Should have edges connecting the chain
      const edgeCount = Object.keys(srg.edges).length;
      assert.ok(edgeCount >= 3, `Expected at least 3 edges, got ${edgeCount}`);
      
      // Should have edges from Root
      const rootEdges = Object.values(srg.edges).filter(e => e.source === 'Root');
      assert.ok(rootEdges.length > 0, 'Should have edges from Root');
    });

    it('should auto-prepend root for chained paths', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
path p: all(p1) => any(p2) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have Root node
      assert.ok(srg.nodes.Root);
      
      // Should have edge from Root (auto-prepended)
      const rootEdges = Object.values(srg.edges).filter(e => e.source === 'Root');
      assert.ok(rootEdges.length > 0, 'Should auto-prepend Root');
    });

    it('should handle long chains (4+ steps)', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
predicate p3: "condition 3"
predicate p4: "condition 4"
outcome o1: "Result"
path p: root => all(p1) => any(p2) => atleast(1, p3) => exactly(1, p4) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should create multiple aggregators
      assert.ok(Object.keys(srg.aggregators).length >= 4);
      
      // Should create chain of edges
      const edgeCount = Object.keys(srg.edges).length;
      assert.ok(edgeCount >= 5, `Expected at least 5 edges for long chain, got ${edgeCount}`);
    });

    it('should handle multiple chained paths', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result 1"
outcome o2: "Result 2"
path p1: root => all(p1) => o1
path p2: all(p2) => not(p1) => o2
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have both outcomes
      assert.ok(srg.outcomes.o1);
      assert.ok(srg.outcomes.o2);
      
      // All paths should connect from Root
      const rootEdges = Object.values(srg.edges).filter(e => e.source === 'Root');
      assert.ok(rootEdges.length >= 2, 'Should have multiple paths from Root');
    });

    it('should handle single-step chained path (backward compatible)', async () => {
      const source = `
predicate p1: "condition 1"
outcome o1: "Result"
path p: all(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should work like before (backward compatible)
      assert.ok(srg.predicates.p1);
      assert.ok(srg.outcomes.o1);
      
      // Should have Root -> aggregator -> outcome
      const edgeCount = Object.keys(srg.edges).length;
      assert.strictEqual(edgeCount, 2, 'Should have 2 edges for single-step path');
    });

    it('should handle chained paths with named aggregators', async () => {
      const source = `
predicate p1: "condition 1"
predicate p2: "condition 2"
outcome o1: "Result"
define check1: all(p1, p2)
path p: root => check1 => any(p1) => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should have named aggregator
      const namedAgg = Object.values(srg.aggregators).find(a => a.name === 'check1');
      assert.ok(namedAgg, 'Should have named aggregator check1');
      
      // Should work in chain
      assert.ok(Object.keys(srg.edges).length >= 3);
    });
  });

  describe('Citations', () => {
    it('should compile citations with source and regions', async () => {
      const source = `
citation age_requirement: {
  source_ref: "policy-handbook-2024.pdf"
  regions: [
    { page: 12, box: [[0.15, 0.32], [0.83, 0.32], [0.83, 0.44], [0.15, 0.44]] }
  ]
}
predicate is_adult: "Is patient over 18?"
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.citations, 'Should have citations in compiled SRG');
      assert.ok(srg.citations.age_requirement, 'Should have age_requirement citation');
      assert.strictEqual(srg.citations.age_requirement.source_ref, 'policy-handbook-2024.pdf');
      assert.ok(Array.isArray(srg.citations.age_requirement.regions), 'Should have regions array');
      assert.strictEqual(srg.citations.age_requirement.regions.length, 1);
      assert.strictEqual(srg.citations.age_requirement.regions[0].page, 12);
      assert.ok(Array.isArray(srg.citations.age_requirement.regions[0].box));
      assert.strictEqual(srg.citations.age_requirement.regions[0].box.length, 4);
      
      // Verify box coordinates (4 vertices: top-left, top-right, bottom-right, bottom-left)
      const box = srg.citations.age_requirement.regions[0].box;
      assert.deepStrictEqual(box[0], [0.15, 0.32], 'Top-left vertex should match');
      assert.deepStrictEqual(box[1], [0.83, 0.32], 'Top-right vertex should match');
      assert.deepStrictEqual(box[2], [0.83, 0.44], 'Bottom-right vertex should match');
      assert.deepStrictEqual(box[3], [0.15, 0.44], 'Bottom-left vertex should match');
    });

    it('should compile citations with regions', async () => {
      const source = `
citation insurance_multi: {
  source_ref: "insurance-guide.docx"
  regions: [
    { page: 5, box: [[0.1, 0.2], [0.9, 0.2], [0.9, 0.35], [0.1, 0.35]] },
    { page: 6, box: [[0.1, 0.1], [0.9, 0.1], [0.9, 0.4], [0.1, 0.4]] }
  ]
}
predicate has_insurance: "Has insurance?"
outcome approved: "Approved"
path p: all(has_insurance) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.citations.insurance_multi, 'Should have insurance_multi citation');
      assert.strictEqual(srg.citations.insurance_multi.source_ref, 'insurance-guide.docx');
      assert.ok(Array.isArray(srg.citations.insurance_multi.regions), 'Regions should be an array');
      assert.strictEqual(srg.citations.insurance_multi.regions.length, 2);
      
      // Verify first region
      assert.strictEqual(srg.citations.insurance_multi.regions[0].page, 5);
      assert.ok(Array.isArray(srg.citations.insurance_multi.regions[0].box), 'Box should be an array');
      assert.strictEqual(srg.citations.insurance_multi.regions[0].box.length, 4);
      const box1 = srg.citations.insurance_multi.regions[0].box;
      assert.deepStrictEqual(box1[0], [0.1, 0.2], 'Region 1: Top-left vertex should match');
      assert.deepStrictEqual(box1[1], [0.9, 0.2], 'Region 1: Top-right vertex should match');
      assert.deepStrictEqual(box1[2], [0.9, 0.35], 'Region 1: Bottom-right vertex should match');
      assert.deepStrictEqual(box1[3], [0.1, 0.35], 'Region 1: Bottom-left vertex should match');
      
      // Verify second region
      assert.strictEqual(srg.citations.insurance_multi.regions[1].page, 6);
      assert.ok(Array.isArray(srg.citations.insurance_multi.regions[1].box), 'Box should be an array');
      assert.strictEqual(srg.citations.insurance_multi.regions[1].box.length, 4);
      const box2 = srg.citations.insurance_multi.regions[1].box;
      assert.deepStrictEqual(box2[0], [0.1, 0.1], 'Region 2: Top-left vertex should match');
      assert.deepStrictEqual(box2[1], [0.9, 0.1], 'Region 2: Top-right vertex should match');
      assert.deepStrictEqual(box2[2], [0.9, 0.4], 'Region 2: Bottom-right vertex should match');
      assert.deepStrictEqual(box2[3], [0.1, 0.4], 'Region 2: Bottom-left vertex should match');
    });

    it('should compile multiple citations', async () => {
      const source = `
citation age_requirement: {
  source_ref: "policy-handbook-2024.pdf"
  regions: [
    { page: 12, box: [[0.15, 0.32], [0.83, 0.32], [0.83, 0.44], [0.15, 0.44]] }
  ]
}
citation er_protocol: {
  source_ref: "ER-triage-guidelines.pdf"
  regions: [
    { page: 8, box: [[0.1, 0.4], [0.85, 0.4], [0.85, 0.6], [0.1, 0.6]] }
  ]
}
predicate is_adult: "Is patient over 18?"
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.citations, 'Should have citations in compiled SRG');
      assert.strictEqual(Object.keys(srg.citations).length, 2);
      assert.ok(srg.citations.age_requirement);
      assert.ok(srg.citations.er_protocol);
    });

    it('should compile citations with optional excerpt', async () => {
      const source = `
citation ada_section: {
  source_ref: "https://www.ada.gov/guide.pdf"
  regions: [
    { page: 3, box: [[0.2, 0.5], [0.8, 0.5], [0.8, 0.6], [0.2, 0.6]] }
  ]
  excerpt: "Age verification requirements"
}
predicate is_adult: "Is patient over 18?"
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.citations.ada_section);
      assert.strictEqual(srg.citations.ada_section.excerpt, 'Age verification requirements');
    });

    it('should compile citations with content hash and filename', async () => {
      const source = `
citation age_requirement: {
  source_ref: "sha256:abc123def456"
  filename: "policy-handbook-2024.pdf"
  regions: [
    { page: 12, box: [[0.15, 0.32], [0.83, 0.32], [0.83, 0.44], [0.15, 0.44]] }
  ]
}
predicate is_adult: "Is patient over 18?"
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.citations.age_requirement);
      assert.strictEqual(srg.citations.age_requirement.source_ref, 'sha256:abc123def456');
      assert.strictEqual(srg.citations.age_requirement.filename, 'policy-handbook-2024.pdf');
      assert.ok(Array.isArray(srg.citations.age_requirement.regions));
      assert.strictEqual(srg.citations.age_requirement.regions.length, 1);
    });

    it('should handle predicates referencing citations', async () => {
      const source = `
citation age_requirement: {
  source_ref: "policy-handbook-2024.pdf"
  regions: [
    { page: 12, box: [[0.15, 0.32], [0.83, 0.32], [0.83, 0.44], [0.15, 0.44]] }
  ]
}
predicate is_adult: "Is patient over 18?"
  cite: age_requirement
  context: "Adults must be 18 or older"
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.predicates.is_adult.citation_ids, 'Predicate should have citation_ids property');
      assert.ok(Array.isArray(srg.predicates.is_adult.citation_ids));
      assert.strictEqual(srg.predicates.is_adult.citation_ids[0], 'age_requirement');
    });

    it('should handle predicates with multiple citations', async () => {
      const source = `
citation age_requirement: {
  source_ref: "policy-handbook-2024.pdf"
  regions: [
    { page: 12, box: [[0.15, 0.32], [0.83, 0.32], [0.83, 0.44], [0.15, 0.44]] }
  ]
}
citation ada_compliance: {
  source_ref: "ada-guide.pdf"
  regions: [
    { page: 3, box: [[0.2, 0.5], [0.8, 0.5], [0.8, 0.6], [0.2, 0.6]] }
  ]
}
predicate is_adult: "Is patient over 18?"
  cite: [age_requirement, ada_compliance]
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.ok(srg.predicates.is_adult.citation_ids);
      assert.strictEqual(srg.predicates.is_adult.citation_ids.length, 2);
      assert.strictEqual(srg.predicates.is_adult.citation_ids[0], 'age_requirement');
      assert.strictEqual(srg.predicates.is_adult.citation_ids[1], 'ada_compliance');
    });

    it('should not include citations field when no citations defined', async () => {
      const source = `
predicate is_adult: "Is patient over 18?"
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      assert.strictEqual(srg.citations, undefined, 'Should not have citations field when none defined');
    });
  });

  describe('Common Properties', () => {
    it('should handle all common properties on predicates', async () => {
      const source = `
citation age_req: {
  source_ref: "policy.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}
predicate is_adult: "Is patient 18?"
  label: "Adult Status Check"
  doc: "Verifies minimum age requirement"
  cite: age_req
  context: "Check DOB"
  metadata: {
    priority: 1
  }
outcome approved: "Approved"
path p: all(is_adult) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const pred = srg.predicates.is_adult;
      assert.strictEqual(pred.label, 'Adult Status Check');
      assert.strictEqual(pred.doc, 'Verifies minimum age requirement');
      assert.deepStrictEqual(pred.citation_ids, ['age_req']);
      assert.strictEqual(pred.context, 'Check DOB');
      assert.strictEqual(pred.metadata.priority, 1);
    });

    it('should handle all common properties on outcomes', async () => {
      const source = `
citation approval_policy: {
  source_ref: "policy.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}
predicate p1: "Test"
outcome approved: "Request approved"
  label: "Fully Approved"
  doc: "Patient meets all requirements"
  cite: approval_policy
  metadata: {
    notification_required: true
  }
path p: all(p1) => approved
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const outcome = srg.outcomes.approved;
      assert.strictEqual(outcome.label, 'Fully Approved');
      assert.strictEqual(outcome.doc, 'Patient meets all requirements');
      assert.deepStrictEqual(outcome.citation_ids, ['approval_policy']);
      assert.strictEqual(outcome.metadata.notification_required, true);
    });

    it('should handle all common properties on aggregators', async () => {
      const source = `
citation policy_doc: {
  source_ref: "policy.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}
predicate p1: "Test 1"
predicate p2: "Test 2"
outcome o1: "Result"
define check: all(p1, p2)
  label: "Basic Check"
  doc: "Combined validation"
  cite: policy_doc
  metadata: {
    version: 2
  }
path p: check => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      const agg = Object.values(srg.aggregators).find(a => a.name === 'check');
      assert.ok(agg);
      assert.strictEqual(agg.label, 'Basic Check');
      assert.strictEqual(agg.doc, 'Combined validation');
      assert.deepStrictEqual(agg.citation_ids, ['policy_doc']);
      assert.strictEqual(agg.metadata.version, 2);
    });

    it('should handle all common properties on paths', async () => {
      const source = `
citation flow_doc: {
  source_ref: "policy.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}
predicate p1: "Test"
outcome o1: "Result"
path test_path: p1 => o1
  label: "Test Path"
  doc: "Standard approval flow"
  cite: flow_doc
  metadata: {
    priority: 1
  }
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Path properties are not included in SRG output (not in schema)
      // Edges are created correctly
      const edges = Object.values(srg.edges);
      assert.ok(edges.length > 0);
      for (const edge of edges) {
        assert.ok(edge.source);
        assert.ok(edge.target);
        assert.strictEqual(typeof edge.condition, 'boolean');
      }
    });

    it('should handle components without common properties', async () => {
      const source = `
predicate p1: "Test"
outcome o1: "Result"
define check: all(p1)
path p: check => o1
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Components without properties should still work
      assert.ok(srg.predicates.p1);
      assert.ok(srg.outcomes.o1);
      const agg = Object.values(srg.aggregators).find(a => a.name === 'check');
      assert.ok(agg);
    });

  });

  describe('Definition Order', () => {
    it('should allow paths to be defined before aggregators they reference', async () => {
      const source = `
predicate p1: "Test 1"
predicate p2: "Test 2"
outcome o1: "Result"

# Path defined before aggregator
path test_path: my_aggregator => o1

# Aggregator defined after path
define my_aggregator: all(p1, p2)
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should compile successfully - edges should be created
      assert.ok(Object.keys(srg.edges).length > 0, 'Should have edges even with forward reference');
      
      // Should have the aggregator
      const agg = Object.values(srg.aggregators).find(a => a.name === 'my_aggregator');
      assert.ok(agg, 'Should have aggregator even though it was defined after path');
    });

    it('should allow citations to be defined after they are referenced', async () => {
      const source = `
# Predicate references citation before it's defined
predicate is_adult: "Is patient 18?"
  cite: age_requirement

outcome approved: "Approved"
path p: all(is_adult) => approved

# Citation defined after being referenced
citation age_requirement: {
  source_ref: "policy.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should compile successfully
      assert.ok(srg.predicates.is_adult);
      assert.ok(srg.predicates.is_adult.citation_ids);
      assert.strictEqual(srg.predicates.is_adult.citation_ids[0], 'age_requirement');
      assert.ok(srg.citations);
      assert.ok(srg.citations.age_requirement);
    });

    it('should allow outcomes to be defined after paths that reference them', async () => {
      const source = `
predicate p1: "Test"
# Path references outcome before it's defined
path test_path: all(p1) => my_outcome

# Outcome defined after path
outcome my_outcome: "My Result"
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should compile successfully
      assert.ok(srg.outcomes.my_outcome);
      assert.ok(Object.keys(srg.edges).length > 0);
    });

    it('should allow complex forward references', async () => {
      const source = `
# Path references aggregator and outcome before they're defined
path complex: my_agg => my_outcome

# Aggregator references predicate before it's defined
define my_agg: all(my_pred)

# Predicate references citation before it's defined
predicate my_pred: "Test"
  cite: my_citation

# Citation defined last
citation my_citation: {
  source_ref: "doc.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}

# Outcome defined last
outcome my_outcome: "Result"
`;
      
      const ast = await parse(source);
      const srg = compile(ast);
      
      // Should compile successfully with all forward references resolved
      assert.ok(srg.outcomes.my_outcome, 'Should have outcome defined after path');
      assert.ok(srg.predicates.my_pred, 'Should have predicate defined after aggregator');
      assert.ok(srg.citations.my_citation, 'Should have citation defined after predicate');
      
      const agg = Object.values(srg.aggregators).find(a => a.name === 'my_agg');
      assert.ok(agg, 'Should have aggregator defined after path');
      
      // Should have edges created
      assert.ok(Object.keys(srg.edges).length > 0, 'Should have edges even with all forward references');
    });
  });
});

describe('Define cycles', () => {
  it('rejects a define that refers to itself at the reference', async () => {
    const error = await compileSource('predicate a: "A?"\noutcome y: "Y"\ndefine d: all(a, e)\ndefine e: not(d)\npath p: d => y').catch(e => e);
    assert.ok(error instanceof CompilerError, String(error));
    assert.match(error.message, /refers to itself: d -> e -> d/);
    assert.deepStrictEqual([error.loc.start.line, error.loc.start.column], [3, 14]);
  });
});

describe('Conditional edges and shared prefixes', () => {
  for (const operator of ['not', 'all']) {
    it(`compiles and shares deeply nested ${operator} prefixes`, async () => {
      const depth = 30;
      const expression = `${operator}(`.repeat(depth) + 'p' + ')'.repeat(depth);
      const srg = compile(await parse(`
predicate p: "P"
outcome x: "X"
outcome y: "Y"
path yes: root => ${expression} => x
path no: ${expression} !=> y
`));
      assert.equal(Object.keys(srg.aggregators).length, depth);
      assert.equal(Object.keys(srg.nodes).length, 4);
      const entryEdges = Object.values(srg.edges).filter(e => e.source === 'Root');
      assert.equal(entryEdges.length, 1);
      const branches = Object.values(srg.edges).filter(e => e.source === entryEdges[0].target);
      assert.deepEqual(branches.map(e => [e.condition, srg.nodes[e.target].item_id]), [
        [true, 'x'],
        [false, 'y'],
      ]);
    });
  }
  it('compiles the MSK fixture to four branches without duplicating decisions', async () => {
    const { readFile } = await import('node:fs/promises');
    const source = await readFile(new URL('../../../tests/fixtures/msk-branches.srg', import.meta.url), 'utf8');
    const srg = compile(await parse(source));
    assert.equal(Object.keys(srg.nodes).length, 14);
    assert.equal(Object.keys(srg.edges).length, 22);
    assert.equal(Object.keys(srg.aggregators).length, 8);
    assert.equal(Object.values(srg.edges).filter(e => e.source === 'Root').length, 4);
    const byName = Object.fromEntries(Object.values(srg.aggregators).map(a => [a.name, a]));
    assert.equal(byName.support_need.label, 'Support need');
    assert.ok(byName.home_criteria.argument_ids.includes(byName.support_need.id));
    assert.ok(byName.facility_criteria.argument_ids.includes(byName.support_need.id));
    const homeNode = Object.values(srg.nodes).find(n => n.item_id === byName.home_criteria.id);
    const fallback = Object.values(srg.edges).find(e => e.source === homeNode.id && !e.condition);
    assert.equal(srg.nodes[fallback.target].item_id, byName.facility_criteria.id);
  });
  it('keeps nodes separate after paths diverge on edge polarity', async () => {
    const srg = compile(await parse(`
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path yes: a => b => x
path no: a !=> b => y
`));
    assert.equal(Object.values(srg.nodes).filter(n => n.item_id === 'a').length, 1);
    assert.equal(Object.values(srg.nodes).filter(n => n.item_id === 'b').length, 2);
  });
  it('shares inline prefixes independently of locations and explicit root', async () => {
    const srg = compile(await parse(`
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path yes: root => all(a, b) => x
path no: all(a, b) !=> y
`));
    assert.equal(Object.keys(srg.aggregators).length, 1);
    assert.equal(Object.values(srg.edges).filter(e => e.source === 'Root').length, 1);
  });
  it('keeps opposite edges to the same outcome and rejects mismatched AST conditions', async () => {
    const ast = await parse('predicate p: "P"\noutcome o: "O"\npath yes: p => o\npath no: p !=> o');
    const srg = compile(ast);
    const node = Object.values(srg.nodes).find(n => n.item_id === 'p');
    assert.deepEqual(Object.values(srg.edges).filter(e => e.source === node.id).map(e => e.condition).sort(), [false, true]);
    ast.definitions.at(-1).conditions = [true, false];
    assert.throws(() => compile(ast), /one boolean per step/);
  });
});

describe('compileFile', () => {
  let dir;
  let files = 0;
  before(() => { dir = fs.mkdtempSync(path.join(os.tmpdir(), 'srg-file-')); });
  after(() => fs.rmSync(dir, { recursive: true, force: true }));

  function writePolicy(bytes) {
    const file = path.join(dir, `policy-${files++}.srg`);
    fs.writeFileSync(file, bytes);
    return file;
  }

  it('rejects a file that is not valid UTF-8 and names it', async () => {
    const file = writePolicy(Buffer.from('predicate a: "Caf\xe9?"\noutcome y: "Y"\npath p: a => y\n', 'latin1'));
    await assert.rejects(compileFile(file), { message: `${file} is not valid UTF-8` });
  });

  it('compiles a UTF-8 file, with or without a BOM', async () => {
    const source = 'predicate a: "Café?"\noutcome y: "Y"\npath p: a => y\n';
    for (const prefix of ['', '\ufeff']) {
      const srg = await compileFile(writePolicy(prefix + source));
      assert.strictEqual(srg.predicates.a.question, 'Café?');
    }
  });

  it('reports the same error location for a file with a BOM as for its source', async () => {
    const source = '\ufeffpredicate 1a: "Q"\n';
    const fromSource = await compileSource(source).catch(error => error);
    const fromFile = await compileFile(writePolicy(source)).catch(error => error);
    assert.ok(fromSource.loc);
    assert.deepStrictEqual(fromFile.loc, fromSource.loc);
  });
});

describe('Invalid AST input', () => {
  const source = steps => `predicate a: "A"\noutcome o: "O"\npath p: ${steps}`;
  const path = ast => ast.definitions[ast.definitions.length - 1];
  for (const [steps, corrupt, message, at] of [
    ['a => o', ast => { path(ast).steps = []; }, "Path 'p' has no steps", 'path'],
    ['all(a) => o', ast => { path(ast).steps[0].args = []; }, 'Aggregators require at least one argument', 'step'],
    ['atleast(1, a) => o', ast => { path(ast).steps[0].count = 0; }, "'atleast' needs a whole-number count from 1 to 9007199254740991", 'step'],
    ['atleast(1, a) => o', ast => { path(ast).steps[0].count = 1.5; }, "'atleast' needs a whole-number count from 1 to 9007199254740991", 'step'],
    ['atleast(1, a) => o', ast => { path(ast).steps[0].count = 1e21; }, "'atleast' needs a whole-number count from 1 to 9007199254740991", 'step'],
    ['atleast(1, a) => o', ast => { delete path(ast).steps[0].count; }, "'atleast' needs a whole-number count from 1 to 9007199254740991", 'step'],
    ['all(a) => o', ast => { delete path(ast).steps[0].args; }, 'Aggregators require at least one argument', 'step'],
    ['not(a) => o', ast => { delete path(ast).steps[0].expr; }, "'not' needs an expression", 'step'],
    ['atmost(1, a) => o', ast => { path(ast).steps[0].count = -1; }, "'atmost' needs a whole-number count from 0 to 9007199254740991", 'step'],
    ['exactly(1, a) => o', ast => { path(ast).steps[0].count = 1.5; }, "'exactly' needs a whole-number count from 0 to 9007199254740991", 'step'],
  ]) {
    it(`rejects ${message} (${steps})`, async () => {
      const ast = await parse(source(steps));
      const expected = at === 'path' ? path(ast).loc : path(ast).steps[0].loc;
      corrupt(ast);
      const error = (() => { try { compile(ast); } catch (e) { return e; } })();
      assert.ok(error instanceof CompilerError, String(error));
      assert.match(error.message, new RegExp(message.replace(/[()]/g, '\\$&')));
      assert.deepStrictEqual(error.loc, expected);
    });
  }
});

describe('AST shape', () => {
  const source = 'predicate sanctioned: "On a sanctions list?"\noutcome approved: "Approved"\noutcome denied: "Denied"\npath block: sanctioned => denied\npath ok: sanctioned !=> approved';
  const pathNamed = (ast, id) => ast.definitions.find(d => d.type === 'path' && d.id === id);
  for (const [name, corrupt, message, at] of [
    ['an unknown definition type', ast => { pathNamed(ast, 'block').type = 'path_definition'; }, "Unknown definition type 'path_definition'", ast => ast.definitions[3].loc],
    ['an unknown key on a path', ast => { const p = pathNamed(ast, 'ok'); p.condition = p.conditions; delete p.conditions; }, "Unknown key 'condition' on path", ast => pathNamed(ast, 'ok').loc],
    ['an unknown key on an expression', ast => { pathNamed(ast, 'ok').steps[0].negated = true; }, "Unknown key 'negated' on reference", ast => pathNamed(ast, 'ok').steps[0].loc],
  ]) {
    it(`rejects ${name}`, async () => {
      const ast = await parse(source);
      const expected = at(ast);
      corrupt(ast);
      const error = (() => { try { compile(ast); } catch (e) { return e; } })();
      assert.ok(error instanceof CompilerError, String(error));
      assert.strictEqual(error.message, message);
      assert.deepStrictEqual(error.loc, expected);
    });
  }

  for (const [name, corrupt, message, at] of [
    ['a type named after an Object member', ast => { ast.definitions[0].type = 'constructor'; }, "Unknown definition type 'constructor'", ast => ast.definitions[0].loc],
    ['a misspelled citation reference key', ast => { const p = pathNamed(ast, 'ok'); p.citation_refs = [{ ref: 'c1', loc: p.loc }]; }, "Unknown key 'ref' in citation_refs of path", ast => pathNamed(ast, 'ok').loc],
    ['an unknown key on outcome_ref', ast => { pathNamed(ast, 'ok').outcome_ref.negated = true; }, "Unknown key 'negated' in outcome_ref of path", ast => pathNamed(ast, 'ok').loc],
    ['an unknown key on loc', ast => { pathNamed(ast, 'ok').loc.foo = 1; }, "Unknown key 'foo' in loc of path", ast => ({ ...pathNamed(ast, 'ok').loc })],
    ['a null step', ast => { pathNamed(ast, 'ok').steps[0] = null; }, 'Expected an expression node in path', ast => pathNamed(ast, 'ok').loc],
    ['a step whose loc is not a location', ast => { pathNamed(ast, 'ok').steps[0].loc = 'nowhere'; }, 'Expected a location in loc of reference', ast => pathNamed(ast, 'ok').loc],
    ['a path whose loc has no offset', ast => { delete pathNamed(ast, 'ok').loc.start.offset; }, 'Expected a location in loc of path', () => ({ start: { line: 0, column: 0, offset: 0 }, end: { line: 0, column: 0, offset: 0 } })],
    ['an outcome_ref whose loc is not a location', ast => { pathNamed(ast, 'ok').outcome_ref.loc = 'nowhere'; }, 'Expected a location in loc of outcome_ref of path', ast => pathNamed(ast, 'ok').loc],
  ]) {
    it(`rejects ${name}`, async () => {
      const ast = await parse(source);
      const expected = at(ast);
      corrupt(ast);
      const error = (() => { try { compile(ast); } catch (e) { return e; } })();
      assert.ok(error instanceof CompilerError, String(error));
      assert.strictEqual(error.message, message);
      assert.deepStrictEqual({ start: error.loc.start, end: error.loc.end }, { start: expected.start, end: expected.end });
    });
  }

  it('rejects an unknown key on the source file', async () => {
    const ast = await parse(source);
    ast.policy_context = 'x';
    assert.throws(() => compile(ast), /Unknown key 'policy_context' on the source file/);
  });

  it('keeps the base check for args that are not an array', async () => {
    const ast = await parse('predicate a: "A"\noutcome o: "O"\npath p: all(a) => o');
    ast.definitions[2].steps[0].args = 5;
    assert.throws(() => compile(ast), /Aggregators require at least one argument/);
  });

  it('ignores keys whose value is undefined, as JSON does', async () => {
    const ast = await parse(source);
    pathNamed(ast, 'ok').label = undefined;
    compile(ast);
  });

  it('lists the same keys per node type as the AST schema', () => {
    const schema = JSON.parse(fs.readFileSync(new URL('../../../schemas/srg-ast-v1.json', import.meta.url), 'utf8'));
    const fromSchema = Object.fromEntries(
      Object.values(schema.definitions)
        .filter(d => d.properties?.type?.const)
        .map(d => [d.properties.type.const, Object.keys(d.properties).sort()]),
    );
    const fromCompiler = Object.fromEntries(
      Object.entries(AST_KEYS).map(([type, keys]) => [type, [...keys].sort()]),
    );
    assert.deepStrictEqual(fromCompiler, fromSchema);
    const nested = { citation_refs: 'CitationReference', outcome_ref: 'OutcomeReference', loc: 'Location', position: 'Position', regions: 'CitationRegion' };
    for (const [key, definition] of Object.entries(nested)) {
      assert.deepStrictEqual([...NESTED_KEYS[key]].sort(), Object.keys(schema.definitions[definition].properties).sort(), key);
    }
    assert.deepStrictEqual([...NESTED_KEYS.source_file].sort(), Object.keys(schema.properties).sort());
  });
});

describe('Undefined references', () => {
  for (const [line, typo] of [['path p: a => bb => y', 'bb'], ['path p: a => nope', 'nope']]) {
    it(`reports the location of '${typo}'`, async () => {
      const error = await compileSource(`predicate a: "A"\noutcome y: "Y"\n${line}`).catch(e => e);
      assert.ok(error instanceof CompilerError, String(error));
      assert.deepStrictEqual(
        [error.loc.start.line, error.loc.start.column, error.loc.end.column],
        [2, line.indexOf(typo), line.indexOf(typo) + typo.length]
      );
    });
  }
});

describe('Citation references', () => {
  for (const [source, message, reference] of [
    ['citation c: { source_ref: "s" }\npredicate p: "Q"\n  cite: d', "Citation 'd' is not defined", 'd'],
    ['outcome o: "O"\n  cite: d', "Citation 'd' is not defined", 'd'],
    ['predicate p: "Q"\ndefine unused: all(p)\n  cite: d', "Citation 'd' is not defined", 'd'],
    ['citation c: { source_ref: "s" }\npredicate p: "Q"\n  cite: [c, c]', "Citation 'c' is cited twice", 'c]'],
    ['predicate p: "Q"\noutcome o: "O"\n  cite: p', "'p' is a predicate; cite: takes citation ids", 'p'],
  ]) {
    it(`rejects ${message} at the reference`, async () => {
      const error = await compileSource(source).catch(e => e);
      assert.ok(error instanceof CompilerError, String(error));
      assert.match(error.message, new RegExp(message));
      const lines = source.split('\n');
      assert.deepStrictEqual(
        [error.loc.start.line, error.loc.start.column],
        [lines.length - 1, lines[lines.length - 1].lastIndexOf(reference)],
      );
    });
  }

  it('accepts a citation declared after the cite', async () => {
    const srg = await compileSource('predicate p: "Q"\n  cite: [c, d]\ncitation c: { source_ref: "s" }\ncitation d: { source_ref: "t" }');
    assert.deepStrictEqual(srg.predicates.p.citation_ids, ['c', 'd']);
  });
});

describe('Identifiers', () => {
  it('rejects a second definition of a name at its location', async () => {
    const error = await compileSource('predicate a: "A?"\noutcome a: "Again"').catch(e => e);
    assert.ok(error instanceof CompilerError, String(error));
    assert.match(error.message, /already defined as a predicate/);
    assert.strictEqual(error.loc.start.line, 1);
  });

  it('names the earlier kind with the right article', async () => {
    const error = await compileSource('outcome a: "A"\npredicate a: "Again?"').catch(e => e);
    assert.ok(error instanceof CompilerError, String(error));
    assert.strictEqual(error.message, "'a' is already defined as an outcome");
    const define = await compileSource('predicate b: "B?"\ndefine d: all(b)\ndefine d: all(b)').catch(e => e);
    assert.strictEqual(define.message, "'d' is already defined as a define");
  });

  it('rejects a definition named like the graph root', async () => {
    const error = await compileSource('predicate root: "Q?"').catch(e => e);
    assert.ok(error instanceof CompilerError, String(error));
    assert.match(error.message, /reserved for the graph root/);
  });

  for (const name of ['A1', 'SN_2', 'SN3', 'Root']) {
    it(`rejects a definition named like a graph id: ${name}`, async () => {
      const error = await compileSource(`predicate b: "B?"\noutcome y: "Y"\npath p: b => y\npredicate ${name}: "Q?"`).catch(e => e);
      assert.ok(error instanceof CompilerError, String(error));
      assert.strictEqual(error.message, `'${name}' is reserved for graph ids`);
      assert.strictEqual(error.loc.start.line, 3);
    });
  }
});

describe('Identifiers and object prototypes', () => {
  for (const source of ['predicate a: "A?"\noutcome y: "Y"\npath p: toString => y', 'predicate a: "A?"\noutcome y: "Y"\npath p: a => constructor']) {
    it(`rejects an undefined name inherited from Object: ${source.split('path p: ')[1]}`, async () => {
      await assert.rejects(compileSource(source), /not found/);
    });
  }
});

describe('Root placement', () => {
  it('rejects root after the first step at the reference', async () => {
    const error = await compileSource('predicate a: "A?"\noutcome y: "Y"\npath p: a => root => y').catch(e => e);
    assert.ok(error instanceof CompilerError, String(error));
    assert.match(error.message, /can only start a path/);
    assert.deepStrictEqual([error.loc.start.line, error.loc.start.column], [2, 13]);
  });

  it('keeps an explicit root at the start of a path', async () => {
    const srg = await compileSource('predicate a: "A?"\noutcome y: "Y"\npath p: root => a => y');
    assert.deepStrictEqual(Object.values(srg.edges).map(e => e.source), ['Root', 'SN_2']);
  });
});

// pnpm installs only declared dependencies, so a caller of compile() can catch
// only the error classes that @anteriorai/srg-compiler itself exports.
describe('Error classes', () => {
  const invalid = {
    SyntaxError: 'predicat adult: "Is the applicant an adult?"',
    StructuralError: 'citation c: { filename: "policy.pdf" }',
  };
  for (const [name, source] of Object.entries(invalid)) {
    it(`exports the ${name} that compile throws, as a ParseError`, async () => {
      const error = await compileSource(source).catch(e => e);
      assert.strictEqual(typeof srgCompiler[name], 'function', `${name} is not exported`);
      assert.ok(error instanceof srgCompiler[name], String(error));
      assert.ok(error instanceof srgCompiler.ParseError);
      assert.ok(!(error instanceof CompilerError));
    });
  }

  it('keeps errors that are not about the policy out of ParseError and CompilerError', async () => {
    const { ParseError, InternalParserError } = srgCompiler;
    const unreadable = await compileFile(path.join(os.tmpdir(), 'no-such-dir', 'policy.srg')).catch(e => e);
    assert.strictEqual(unreadable.code, 'ENOENT');
    for (const error of [unreadable, new InternalParserError('bug')]) {
      assert.ok(!(error instanceof ParseError), String(error));
      assert.ok(!(error instanceof CompilerError), String(error));
    }
  });
});
