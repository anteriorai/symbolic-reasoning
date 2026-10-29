/**
 * GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from schemas/srg-ast-v1.json.
 * To regenerate, run: npm run generate
 */

/**
 * Top-level definition types
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "Definition".
 */
export type Definition =
  PolicyContextDefinition | PredicateDefinition | OutcomeDefinition | AggregatorDefinition | CitationDefinition | Path;
/**
 * Expression types in SRG language
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "Expression".
 */
export type Expression =
  | ReferenceExpression
  | AllExpression
  | AnyExpression
  | NoneExpression
  | AtLeastExpression
  | AtMostExpression
  | ExactlyExpression
  | NotExpression;

/**
 * Root AST node representing a parsed SRG file
 */
export interface SourceFile {
  type: 'source_file';
  /**
   * List of top-level definitions
   */
  definitions: Definition[];
}
/**
 * Policy-wide guidance declaration, preserved in source order
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "PolicyContextDefinition".
 */
export interface PolicyContextDefinition {
  type: 'policy_context_definition';
  value: string;
  loc: Location;
}
/**
 * Source code range
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "Location".
 */
export interface Location {
  start: Position;
  end: Position;
}
/**
 * Location in source code
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "Position".
 */
export interface Position {
  /**
   * Line number (0-indexed)
   */
  line: number;
  /**
   * Column in UTF-16 code units (0-indexed)
   */
  column: number;
  /**
   * Offset in UTF-16 code units from the start of the source
   */
  offset: number;
}
/**
 * Predicate definition in AST
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "PredicateDefinition".
 */
export interface PredicateDefinition {
  type: 'predicate_definition';
  /**
   * Predicate identifier
   */
  id: string;
  /**
   * The question or condition text
   */
  question: string;
  /**
   * Optional human-readable label
   */
  label?: string;
  /**
   * Optional documentation
   */
  doc?: string;
  /**
   * Optional citation references
   */
  citation_refs?: CitationReference[];
  /**
   * Optional context for evaluation
   */
  context?: string;
  /**
   * Optional custom properties
   */
  properties?: {
    [k: string]: unknown;
  };
  loc: Location;
}
/**
 * Reference to a citation with location for go-to-definition
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "CitationReference".
 */
export interface CitationReference {
  /**
   * Citation identifier
   */
  id: string;
  loc: Location;
}
/**
 * Outcome definition in AST
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "OutcomeDefinition".
 */
export interface OutcomeDefinition {
  type: 'outcome_definition';
  /**
   * Outcome identifier
   */
  id: string;
  /**
   * Description of the outcome
   */
  description: string;
  /**
   * Optional human-readable label
   */
  label?: string;
  /**
   * Optional documentation
   */
  doc?: string;
  /**
   * Optional citation references
   */
  citation_refs?: CitationReference[];
  /**
   * Optional custom properties
   */
  properties?: {
    [k: string]: unknown;
  };
  loc: Location;
}
/**
 * Aggregator definition in AST
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "AggregatorDefinition".
 */
export interface AggregatorDefinition {
  type: 'aggregator_definition';
  /**
   * Aggregator identifier
   */
  id: string;
  expression: Expression;
  /**
   * Optional human-readable label
   */
  label?: string;
  /**
   * Optional documentation
   */
  doc?: string;
  /**
   * Optional citation references
   */
  citation_refs?: CitationReference[];
  /**
   * Optional custom properties
   */
  properties?: {
    [k: string]: unknown;
  };
  loc: Location;
}
/**
 * Reference to a predicate or named aggregator
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "ReferenceExpression".
 */
export interface ReferenceExpression {
  type: 'reference';
  /**
   * Identifier being referenced
   */
  id: string;
  loc: Location;
}
/**
 * all(arg1, arg2, ...) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "AllExpression".
 */
export interface AllExpression {
  type: 'all';
  args: Expression[];
  loc: Location;
}
/**
 * any(arg1, arg2, ...) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "AnyExpression".
 */
export interface AnyExpression {
  type: 'any';
  args: Expression[];
  loc: Location;
}
/**
 * none(arg1, arg2, ...) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "NoneExpression".
 */
export interface NoneExpression {
  type: 'none';
  args: Expression[];
  loc: Location;
}
/**
 * atleast(count, arg1, arg2, ...) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "AtLeastExpression".
 */
export interface AtLeastExpression {
  type: 'atleast';
  /**
   * Minimum number of arguments that must be true
   */
  count: number;
  args: Expression[];
  loc: Location;
}
/**
 * atmost(count, arg1, arg2, ...) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "AtMostExpression".
 */
export interface AtMostExpression {
  type: 'atmost';
  /**
   * Maximum number of arguments that can be true
   */
  count: number;
  args: Expression[];
  loc: Location;
}
/**
 * exactly(count, arg1, arg2, ...) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "ExactlyExpression".
 */
export interface ExactlyExpression {
  type: 'exactly';
  /**
   * Exact number of arguments that must be true
   */
  count: number;
  args: Expression[];
  loc: Location;
}
/**
 * not(expr) expression
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "NotExpression".
 */
export interface NotExpression {
  type: 'not';
  expr: Expression;
  loc: Location;
}
/**
 * Citation definition in AST
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "CitationDefinition".
 */
export interface CitationDefinition {
  type: 'citation_definition';
  /**
   * Citation identifier
   */
  id: string;
  /**
   * Reference to the source document
   */
  source_ref: string;
  /**
   * Optional filename
   */
  filename?: string;
  /**
   * Optional regions (bounding boxes)
   */
  regions?: CitationRegion[];
  /**
   * Optional excerpt from source
   */
  excerpt?: string;
  /**
   * Optional additional metadata
   */
  metadata?: {
    [k: string]: unknown;
  };
  loc: Location;
}
/**
 * A region within a document page defined by a bounding box
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "CitationRegion".
 */
export interface CitationRegion {
  /**
   * Page number (0-indexed)
   */
  page: number;
  /**
   * Bounding box defined by 4 vertices: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
   *
   * @minItems 4
   * @maxItems 4
   */
  box: [[number, number], [number, number], [number, number], [number, number]];
}
/**
 * Path definition connecting expressions to outcomes
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "Path".
 */
export interface Path {
  type: 'path';
  /**
   * Path identifier
   */
  id: string;
  /**
   * Optional human-readable label
   */
  label?: string;
  /**
   * Optional documentation
   */
  doc?: string;
  /**
   * Chain of expressions (e.g., [root, all(p1, p2), any(p3, p4)])
   */
  steps: Expression[];
  outcome_ref: OutcomeReference;
  /**
   * Optional citation references
   */
  citation_refs?: CitationReference[];
  /**
   * Optional custom properties
   */
  properties?: {
    [k: string]: unknown;
  };
  loc: Location;
  /**
   * Outgoing edge condition for each step, including the final edge to the outcome. Omitted means all true; when present, length must equal steps.
   *
   * @minItems 1
   */
  conditions?: [boolean, ...boolean[]];
}
/**
 * Reference to an outcome with location for go-to-definition
 *
 * This interface was referenced by `SourceFile`'s JSON-Schema
 * via the `definition` "OutcomeReference".
 */
export interface OutcomeReference {
  /**
   * Outcome identifier
   */
  id: string;
  loc: Location;
}
