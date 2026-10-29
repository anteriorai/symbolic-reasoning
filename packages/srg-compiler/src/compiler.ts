import type * as AST from '@anteriorai/srg-parser';
import type * as SRG from '@anteriorai/srg-types';
import { AGGREGATOR_ID_PATTERN, NODE_ID_PATTERN } from '@anteriorai/srg-types';

// Keys each AST node type may carry, as in schemas/srg-ast-v1.json (a test keeps them equal).
export const AST_KEYS: Record<string, readonly string[]> = {
  reference: ['type', 'id', 'loc'],
  all: ['type', 'args', 'loc'],
  any: ['type', 'args', 'loc'],
  none: ['type', 'args', 'loc'],
  atleast: ['type', 'count', 'args', 'loc'],
  atmost: ['type', 'count', 'args', 'loc'],
  exactly: ['type', 'count', 'args', 'loc'],
  not: ['type', 'expr', 'loc'],
  predicate_definition: ['type', 'id', 'question', 'context', 'label', 'doc', 'citation_refs', 'properties', 'loc'],
  outcome_definition: ['type', 'id', 'description', 'label', 'doc', 'citation_refs', 'properties', 'loc'],
  aggregator_definition: ['type', 'id', 'expression', 'label', 'doc', 'citation_refs', 'properties', 'loc'],
  citation_definition: ['type', 'id', 'source_ref', 'filename', 'regions', 'excerpt', 'metadata', 'loc'],
  path: ['type', 'id', 'steps', 'conditions', 'outcome_ref', 'label', 'doc', 'citation_refs', 'properties', 'loc'],
  policy_context_definition: ['type', 'value', 'loc'],
};

// Keys of the nested objects the AST schema closes, by the field that holds them.
export const NESTED_KEYS: Record<string, readonly string[]> = {
  citation_refs: ['id', 'loc'],
  outcome_ref: ['id', 'loc'],
  loc: ['start', 'end'],
  position: ['line', 'column', 'offset'],
  regions: ['page', 'box'],
  source_file: ['type', 'definitions'],
};

const EXPRESSION_TYPES = new Set(['reference', 'all', 'any', 'none', 'atleast', 'atmost', 'exactly', 'not']);

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isLocation = (value: unknown): value is AST.Location =>
  isObject(value) &&
  [value.start, value.end].every(end => isObject(end) && NESTED_KEYS.position.every(key => typeof end[key] === 'number'));

// Keys with an undefined value are absent once the AST is JSON, so they are ignored.
function unknownKey(value: object, allowed: readonly string[]): string | undefined {
  return Object.entries(value).find(([key, v]) => v !== undefined && !allowed.includes(key))?.[0];
}

function checkNested(value: unknown, field: string, owner: string, loc: AST.Location): void {
  const where = `in ${field} of ${owner}`;
  if (field === 'loc' && !isLocation(value)) throw new CompilerError(`Expected a location ${where}`, loc);
  if (!isObject(value)) return; // type errors are caught later
  const key = unknownKey(value, NESTED_KEYS[field]);
  if (key !== undefined) throw new CompilerError(`Unknown key '${key}' ${where}`, loc);
  if (field === 'loc') {
    for (const end of ['start', 'end']) {
      const position = value[end];
      if (isObject(position)) {
        const extra = unknownKey(position, NESTED_KEYS.position);
        if (extra !== undefined) throw new CompilerError(`Unknown key '${extra}' ${where}.${end}`, loc);
      }
    }
  }
  if (field !== 'loc' && value.loc !== undefined) checkNested(value.loc, 'loc', `${field} of ${owner}`, loc);
}

// A hand-built AST can hold node types and keys the parser never produces.
function checkShape(node: unknown, expression: boolean, parentLoc: AST.Location, parent: string): void {
  const kind = expression ? 'expression' : 'definition';
  if (!isObject(node) || Array.isArray(node)) {
    throw new CompilerError(`Expected an ${kind} node in ${parent}`, parentLoc);
  }
  const { type, loc } = node;
  if (!isLocation(loc)) throw new CompilerError(`Expected a location in loc of ${String(type)}`, parentLoc);
  if (typeof type !== 'string' || !Object.hasOwn(AST_KEYS, type) || EXPRESSION_TYPES.has(type) !== expression) {
    throw new CompilerError(`Unknown ${kind} type '${String(type)}'`, loc);
  }
  const key = unknownKey(node, AST_KEYS[type]);
  if (key !== undefined) throw new CompilerError(`Unknown key '${key}' on ${type}`, loc);
  checkNested(loc, 'loc', type, loc);
  checkNested(node.outcome_ref, 'outcome_ref', type, loc);
  for (const field of ['citation_refs', 'regions']) {
    const items = node[field];
    if (Array.isArray(items)) for (const item of items) checkNested(item, field, type, loc);
  }
  for (const field of ['args', 'steps']) {
    const children = node[field];
    // Not an array: left to the checks that already report it at this node.
    if (Array.isArray(children)) for (const child of children) checkShape(child, true, loc, type);
  }
  for (const field of ['expr', 'expression']) {
    if (node[field] !== undefined) checkShape(node[field], true, loc, type);
  }
}

// Reject what only a hand-built AST can hold; the parser never produces it. The largest
// count is MAX_SAFE_INTEGER, the largest whole number both JSON and the Python runtime
// read back unchanged.
function checkAggregator(expr: AST.Expression): void {
  if (expr.type === 'reference') return;
  if (expr.type === 'not') {
    if (!expr.expr) throw new CompilerError("'not' needs an expression", expr.loc);
    return;
  }
  if (!Array.isArray(expr.args) || expr.args.length === 0) {
    throw new CompilerError('Aggregators require at least one argument', expr.loc);
  }
  if (expr.type !== 'atleast' && expr.type !== 'atmost' && expr.type !== 'exactly') return;
  const minimum = expr.type === 'atleast' ? 1 : 0;
  const { count } = expr;
  if (!Number.isInteger(count) || count < minimum || count > Number.MAX_SAFE_INTEGER) {
    throw new CompilerError(
      `'${expr.type}' needs a whole-number count from ${minimum} to ${Number.MAX_SAFE_INTEGER}`,
      expr.loc,
    );
  }
}

export class CompilerError extends Error {
  constructor(message: string, public readonly loc: AST.Location) {
    super(message);
    this.name = 'CompilerError';
  }
}

export function compile(ast: AST.SourceFile): SRG.SRG {
  const compiler = new Compiler();
  return compiler.compile(ast);
}

class Compiler {
  private predicates: Map<string, AST.PredicateDefinition> = new Map();
  private outcomes: Map<string, AST.OutcomeDefinition> = new Map();
  private aggregators: Map<string, AST.AggregatorDefinition> = new Map();
  private citations: Map<string, AST.CitationDefinition> = new Map();
  private paths: AST.Path[] = [];
  
  private nodeCounter = 1;
  private aggregatorCounter = 1;
  private prefixNodes = new Map<string, string>();
  private compiledAggregators = new Map<string, string>();
  private resolving: string[] = [];
  private kinds = new Map<string, string>();

  compile(ast: AST.SourceFile): SRG.SRG {
    let policyContext: string | undefined;
    const rootKey = unknownKey(ast, NESTED_KEYS.source_file);
    const fileLoc = { start: { line: 0, column: 0, offset: 0 }, end: { line: 0, column: 0, offset: 0 } };
    if (rootKey !== undefined) {
      throw new CompilerError(`Unknown key '${rootKey}' on the source file`, fileLoc);
    }
    for (const def of ast.definitions) checkShape(def, false, fileLoc, 'the source file');

    // Phase 1: Collect definitions
    for (const def of ast.definitions) {
      switch (def.type) {
        case 'policy_context_definition':
          if (policyContext !== undefined) {
            throw new CompilerError('Duplicate policy_context declaration', def.loc);
          }
          policyContext = def.value;
          break;
        case 'predicate_definition':
          this.claim(def, 'predicate');
          this.predicates.set(def.id, def);
          break;
        case 'outcome_definition':
          this.claim(def, 'outcome');
          this.outcomes.set(def.id, def);
          break;
        case 'aggregator_definition':
          this.claim(def, 'define');
          this.aggregators.set(def.id, def);
          break;
        case 'citation_definition':
          if (this.citations.has(def.id)) {
            throw new CompilerError(`'${def.id}' is already defined as a citation`, def.loc);
          }
          this.citations.set(def.id, def);
          break;
        case 'path':
          this.paths.push(def);
          break;
      }
    }

    // Citations may be declared after a cite, so check once all are known.
    for (const def of ast.definitions) {
      const cited = new Set<string>();
      for (const reference of ('citation_refs' in def && def.citation_refs) || []) {
        if (!this.citations.has(reference.id)) {
          const kind = this.predicates.has(reference.id) ? 'a predicate'
            : this.outcomes.has(reference.id) ? 'an outcome'
            : this.aggregators.has(reference.id) ? 'a define' : undefined;
          throw new CompilerError(
            kind ? `'${reference.id}' is ${kind}; cite: takes citation ids`
              : `Citation '${reference.id}' is not defined`,
            reference.loc,
          );
        }
        if (cited.has(reference.id)) {
          throw new CompilerError(`Citation '${reference.id}' is cited twice`, reference.loc);
        }
        cited.add(reference.id);
      }
    }

    // Phase 2: Build SRG
    const srg: SRG.SRG = {
      predicates: {},
      aggregators: {},
      outcomes: {},
      nodes: {},
      edges: {},
      policy_context: policyContext ?? null,
    };

    // Add citations if any are defined
    if (this.citations.size > 0) {
      const citations: Record<string, SRG.Citation> = {};
      for (const [id, citation] of this.citations) {
        const citationObj: SRG.Citation = {
          source_ref: citation.source_ref,
          ...(citation.filename && { filename: citation.filename }),
          ...(citation.regions && { regions: citation.regions }),
          ...(citation.excerpt && { excerpt: citation.excerpt }),
          ...(citation.metadata && { metadata: citation.metadata }),
        };
        
        citations[id] = citationObj;
      }
      srg.citations = citations;
    }

    // Root node is required by schema
    srg.nodes['Root'] = {
      id: 'Root',
      item_id: 'Root',
    };

    for (const [id, pred] of this.predicates) {
      const citationIds = pred.citation_refs?.map(r => r.id);
      const predicate: SRG.Predicate = {
        type: 'Predicate',
        id,
        question: pred.question,
        ...(pred.context && { context: pred.context }),
        ...(pred.label && { label: pred.label }),
        ...(pred.doc && { doc: pred.doc }),
        ...(citationIds && citationIds.length > 0 && { citation_ids: citationIds }),
        ...(pred.properties && { metadata: pred.properties }),
      };

      srg.predicates[id] = predicate;
    }

    for (const [id, outcome] of this.outcomes) {
      const citationIds = outcome.citation_refs?.map(r => r.id);
      const outcomeObj: SRG.Outcome = {
        type: 'Outcome',
        id,
        description: outcome.description,
        ...(outcome.label && { label: outcome.label }),
        ...(outcome.doc && { doc: outcome.doc }),
        ...(citationIds && citationIds.length > 0 && { citation_ids: citationIds }),
        ...(outcome.properties && { metadata: outcome.properties }),
      };

      srg.outcomes[id] = outcomeObj;
    }

    for (const path of this.paths) {
      if (path.steps.length === 0) {
        throw new CompilerError(`Path '${path.id}' has no steps`, path.loc);
      }
      const outcomeId = path.outcome_ref.id;
      if (!Object.prototype.hasOwnProperty.call(srg.outcomes, outcomeId)) {
        throw new CompilerError(
          `Outcome '${outcomeId}' not found (referenced in path)`,
          path.outcome_ref.loc
        );
      }
      
      let outcomeNode = Object.values(srg.nodes).find(
        (n) => n.item_id === outcomeId
      );
      if (!outcomeNode) {
        const outcomeNodeId = this.nextNodeId();
        outcomeNode = {
          id: outcomeNodeId,
          item_id: outcomeId,
        };
        srg.nodes[outcomeNodeId] = outcomeNode;
      }

      const conditions = path.conditions ?? path.steps.map(() => true);
      if (conditions.length !== path.steps.length) {
        throw new CompilerError('Path conditions must contain one boolean per step', path.loc);
      }
      const firstStep = path.steps[0];
      const startsWithRoot = firstStep.type === 'reference' && firstStep.id === 'root';
      if (startsWithRoot && !conditions[0]) {
        throw new CompilerError('root is always true, so it never takes a false edge', firstStep.loc);
      }
      let source = 'Root';
      for (let index = startsWithRoot ? 1 : 0; index < path.steps.length; index++) {
        const condition = index ? conditions[index - 1] : true;
        const target = this.compileExpression(path.steps[index], srg, source, condition);
        this.addEdge(srg, source, target, condition);
        source = target;
      }
      this.addEdge(srg, source, outcomeNode.id, conditions[conditions.length - 1]);
    }

    return srg;
  }

  /**
   * Create an aggregator and add it to the SRG
   */
  private createAggregator(options: {
    srg: SRG.SRG;
    strategy: SRG.Strategy;
    truthValue: boolean;
    argumentIds: string[];
    name?: string;
    label?: string;
    doc?: string;
    citation_ids?: string[];
    properties?: Record<string, unknown>;
  }): string {
    const {
      srg,
      strategy,
      truthValue,
      argumentIds,
      name = '',
      label,
      doc,
      citation_ids,
      properties
    } = options;
    const aggId = this.nextAggregatorId();
    
    const aggregator: SRG.Aggregator = {
      type: 'Aggregator',
      id: aggId,
      name: name,
      truth_value: truthValue,
      strategy: strategy,
      argument_ids: argumentIds as [string, ...string[]],
      ...(label && { label }),
      ...(doc && { doc }),
      ...(citation_ids && citation_ids.length > 0 && { citation_ids }),
      ...(properties && { metadata: properties }),
    };

    srg.aggregators[aggId] = aggregator;
    return aggId;
  }

  /**
   * Compile an expression and return the item ID (predicate or aggregator ID)
   * This recursively compiles nested expressions and creates aggregators as needed,
   * but does NOT create nodes or edges.
   */
  private compileExpressionToItemId(options: {
    expr: AST.Expression;
    srg: SRG.SRG;
    name?: string;
    label?: string;
    doc?: string;
    properties?: Record<string, unknown>;
    citation_ids?: string[];
  }): string {
    const {
      expr,
      srg,
      name = '',
      label,
      doc,
      properties,
      citation_ids
    } = options;
    checkAggregator(expr);
    switch (expr.type) {
      case 'reference': {
        if (expr.id === 'root') {
          throw new CompilerError('root can only start a path', expr.loc);
        }

        if (Object.prototype.hasOwnProperty.call(srg.predicates, expr.id)) {
          return expr.id;
        }

        const namedAgg = this.aggregators.get(expr.id);
        if (namedAgg) {
          const existing = this.compiledAggregators.get(expr.id);
          if (existing !== undefined) return existing;
          if (this.resolving.includes(expr.id)) {
            const cycle = [...this.resolving.slice(this.resolving.indexOf(expr.id)), expr.id];
            throw new CompilerError(`'${expr.id}' refers to itself: ${cycle.join(' -> ')}`, expr.loc);
          }
          this.resolving.push(expr.id);
          // A define is always its own aggregator, so its name and annotations reach the graph.
          const body = namedAgg.expression;
          // Named symbols are shared; their graph occurrences have separate prefixes.
          const itemId = this.compileExpressionToItemId({
            expr: body.type === 'reference' ? { type: 'all', args: [body], loc: body.loc } : body,
            srg,
            name: expr.id,
            label: namedAgg.label,
            doc: namedAgg.doc,
            properties: namedAgg.properties,
            citation_ids: namedAgg.citation_refs?.map(r => r.id)
          });
          this.resolving.pop();
          this.compiledAggregators.set(expr.id, itemId);
          return itemId;
        }

        throw new CompilerError(
          `Reference '${expr.id}' not found (not a predicate or named aggregator)`,
          expr.loc
        );
      }

      case 'all':
      case 'any':
      case 'none': {
        const argumentIds: string[] = [];
        for (const arg of expr.args) {
          const childItemId = this.compileExpressionToItemId({ expr: arg, srg });
          argumentIds.push(childItemId);
        }

        let strategy: SRG.Strategy;
        let truthValue: boolean;
        
        if (expr.type === 'all') {
          strategy = { type: 'AllStrategy' };
          truthValue = true;
        } else if (expr.type === 'any') {
          strategy = { type: 'AtLeastStrategy', count: 1 };
          truthValue = true;
        } else {
          strategy = { type: 'AllStrategy' };
          truthValue = false;
        }

        return this.createAggregator({
          srg,
          strategy,
          truthValue,
          argumentIds,
          name,
          label,
          doc,
          citation_ids,
          properties
        });
      }

      case 'atleast':
      case 'atmost':
      case 'exactly': {
        const argumentIds: string[] = [];
        for (const arg of expr.args) {
          const childItemId = this.compileExpressionToItemId({ expr: arg, srg });
          argumentIds.push(childItemId);
        }

        let strategy: SRG.Strategy;
        if (expr.type === 'atleast') {
          strategy = { type: 'AtLeastStrategy', count: expr.count };
        } else if (expr.type === 'atmost') {
          strategy = { type: 'AtMostStrategy', count: expr.count };
        } else {
          strategy = { type: 'ExactlyStrategy', count: expr.count };
        }

        return this.createAggregator({
          srg,
          strategy,
          truthValue: true, // atleast/atmost/exactly always use positive logic
          argumentIds,
          name,
          label,
          doc,
          citation_ids,
          properties
        });
      }

      case 'not': {
        const childItemId = this.compileExpressionToItemId({ expr: expr.expr, srg });

        return this.createAggregator({
          srg,
          strategy: { type: 'AllStrategy' },
          truthValue: false,
          argumentIds: [childItemId],
          name,
          label,
          doc,
          citation_ids,
          properties
        });
      }

      default:
        throw new Error(`Unknown expression type: ${(expr as any).type}`);
    }
  }

  private addEdge(srg: SRG.SRG, source: string, target: string, condition: boolean): void {
    const edgeId = `E_${source}->${target}${condition ? '' : ':false'}`;
    srg.edges[edgeId] = { source, target, condition };
  }

  private expressionKey(expr: AST.Expression): unknown[] {
    checkAggregator(expr);
    // Serialize only the complete key to avoid repeatedly escaping child strings.
    if (expr.type === 'reference') return [expr.type, expr.id];
    if (expr.type === 'not') return [expr.type, this.expressionKey(expr.expr)];
    return [expr.type, 'count' in expr ? expr.count : null,
      expr.args.map(arg => this.expressionKey(arg))];
  }

  private compileExpression(expr: AST.Expression, srg: SRG.SRG, source: string, condition: boolean): string {
    // Parent identity includes the full prefix, not just the previous predicate.
    const key = JSON.stringify([source, condition, this.expressionKey(expr)]);
    const existing = this.prefixNodes.get(key);
    if (existing !== undefined) return existing;
    const itemId = this.compileExpressionToItemId({ expr, srg });
    const nodeId = this.nextNodeId();
    srg.nodes[nodeId] = { id: nodeId, item_id: itemId };
    this.prefixNodes.set(key, nodeId);
    return nodeId;
  }

  private nextNodeId(): string {
    return `SN_${this.nodeCounter++}`;
  }

  // Predicates, outcomes and defines share one namespace.
  private claim(
    def: AST.PredicateDefinition | AST.OutcomeDefinition | AST.AggregatorDefinition,
    kind: string
  ): void {
    if (def.id === 'root') {
      throw new CompilerError("'root' is reserved for the graph root", def.loc);
    }
    if (AGGREGATOR_ID_PATTERN.test(def.id) || NODE_ID_PATTERN.test(def.id)) {
      throw new CompilerError(`'${def.id}' is reserved for graph ids`, def.loc);
    }
    const existing = this.kinds.get(def.id);
    if (existing) {
      const article = existing === 'outcome' ? 'an' : 'a';
      throw new CompilerError(`'${def.id}' is already defined as ${article} ${existing}`, def.loc);
    }
    this.kinds.set(def.id, kind);
  }

  private nextAggregatorId(): string {
    return `A${this.aggregatorCounter++}`;
  }
}
