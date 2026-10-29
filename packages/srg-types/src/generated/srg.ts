/**
 * GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * This file is auto-generated from schemas/srg-schema-v1.json
 * To regenerate, run: npm run generate
 *
 * Part of @anteriorai/srg-types package
 */

/**
 * Strategy for aggregating boolean evaluations
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Strategy".
 */
export type Strategy = AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy;

/**
 * Symbolic Reasoning Graph structure, defining predicates, aggregators, outcomes, nodes, and edges
 */
export interface SRG {
  /**
   * Dictionary of predicates keyed by predicate ID
   */
  predicates: {
    [k: string]: Predicate;
  };
  /**
   * Dictionary of aggregators keyed by aggregator ID
   */
  aggregators: {
    [k: string]: Aggregator;
  };
  /**
   * Dictionary of outcomes keyed by outcome ID
   */
  outcomes: {
    [k: string]: Outcome;
  };
  /**
   * Dictionary of graph nodes keyed by node ID. MUST contain a Root node with id='Root' and item_id='Root'. Validated programmatically.
   */
  nodes: {
    [k: string]: Node;
  };
  /**
   * Dictionary of graph edges keyed by edge ID
   */
  edges: {
    [k: string]: Edge;
  };
  /**
   * Optional policy context or general guidance applicable to the entire graph
   */
  policy_context?: string | null;
  /**
   * Dictionary of citation definitions keyed by citation ID
   */
  citations?: {
    [k: string]: Citation;
  };
}
/**
 * A predicate represents a question or condition to be evaluated
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Predicate".
 */
export interface Predicate {
  /**
   * Discriminator field for symbol type
   */
  type: 'Predicate';
  /**
   * Unique identifier for the predicate (e.g., 'P1', 'P2', or human-readable like 'is_adult')
   */
  id: string;
  /**
   * The question or condition text to be evaluated
   */
  question: string;
  /**
   * Human-readable label for the predicate
   */
  label?: string;
  /**
   * Human-readable documentation providing additional details about the predicate
   */
  doc?: string;
  /**
   * Array of citation IDs referencing source documents or policies
   */
  citation_ids?: string[];
  /**
   * Optional additional context for evaluating the predicate
   */
  context?: string | null;
  /**
   * Author-defined annotations; not used during evaluation
   */
  metadata?: {
    [k: string]: unknown;
  };
}
/**
 * An aggregator combines multiple predicates or other aggregators using a logical strategy
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Aggregator".
 */
export interface Aggregator {
  /**
   * Discriminator field for symbol type
   */
  type: 'Aggregator';
  /**
   * Unique identifier for the aggregator (e.g., 'A1', 'A2')
   */
  id: string;
  /**
   * Human-readable name for the aggregator (empty string for unnamed aggregators)
   */
  name: string;
  /**
   * Whether the aggregator uses positive logic (true) or negation (false)
   */
  truth_value: boolean;
  /**
   * The aggregation strategy to apply
   */
  strategy: AllStrategy | AtLeastStrategy | AtMostStrategy | ExactlyStrategy;
  /**
   * IDs of child predicates or aggregators
   *
   * @minItems 1
   */
  argument_ids: [string, ...string[]];
  /**
   * Human-readable label for the aggregator
   */
  label?: string;
  /**
   * Human-readable documentation providing additional details about the aggregator
   */
  doc?: string;
  /**
   * Array of citation IDs referencing source documents or policies
   */
  citation_ids?: string[];
  /**
   * Author-defined annotations; not used during evaluation
   */
  metadata?: {
    [k: string]: unknown;
  };
}
/**
 * All arguments must evaluate to true
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "AllStrategy".
 */
export interface AllStrategy {
  type: 'AllStrategy';
}
/**
 * At least N arguments must evaluate to true
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "AtLeastStrategy".
 */
export interface AtLeastStrategy {
  type: 'AtLeastStrategy';
  /**
   * Minimum number of arguments that must be true
   */
  count: number;
}
/**
 * At most N arguments must evaluate to true
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "AtMostStrategy".
 */
export interface AtMostStrategy {
  type: 'AtMostStrategy';
  /**
   * Maximum number of arguments that can be true
   */
  count: number;
}
/**
 * Exactly N arguments must evaluate to true
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "ExactlyStrategy".
 */
export interface ExactlyStrategy {
  type: 'ExactlyStrategy';
  /**
   * Exact number of arguments that must be true
   */
  count: number;
}
/**
 * An outcome represents a possible result or decision
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Outcome".
 */
export interface Outcome {
  /**
   * Discriminator field for symbol type
   */
  type: 'Outcome';
  /**
   * Unique identifier for the outcome (e.g., 'O1', 'O2', or human-readable like 'approved')
   */
  id: string;
  /**
   * Description of the outcome
   */
  description: string;
  /**
   * Human-readable label for the outcome
   */
  label?: string;
  /**
   * Human-readable documentation providing additional details about the outcome
   */
  doc?: string;
  /**
   * Array of citation IDs referencing source documents or policies
   */
  citation_ids?: string[];
  /**
   * Author-defined annotations; not used during evaluation
   */
  metadata?: {
    [k: string]: unknown;
  };
}
/**
 * A node in the graph that references a symbol (predicate, aggregator, or outcome)
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Node".
 */
export interface Node {
  /**
   * Unique identifier for the node (e.g., 'SN_1', 'SN_2', 'Root')
   */
  id: string;
  /**
   * ID of the predicate, aggregator or outcome this node represents; only the node with id 'Root' has item_id 'Root'
   */
  item_id: string;
}
/**
 * A directed edge connecting two nodes in the graph
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Edge".
 */
export interface Edge {
  /**
   * ID of the source node
   */
  source: string;
  /**
   * ID of the target node
   */
  target: string;
  /**
   * Edge condition
   */
  condition: boolean;
}
/**
 * A citation references a source document or policy with optional bounding boxes and excerpts
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Citation".
 */
export interface Citation {
  /**
   * Reference to the source document (e.g., SHA256 hash, file path, or URL)
   */
  source_ref: string;
  /**
   * Optional filename of the source document
   */
  filename?: string;
  /**
   * Optional array of regions (bounding boxes) within the document
   */
  regions?: CitationRegion[];
  /**
   * Optional excerpt or quote from the source document
   */
  excerpt?: string;
  /**
   * Author-defined annotations; not used during evaluation
   */
  metadata?: {
    [k: string]: unknown;
  };
}
/**
 * A region within a document page defined by a bounding box
 *
 * This interface was referenced by `SRG`'s JSON-Schema
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
 * The root node representing the entry point of the graph
 *
 * This interface was referenced by `SRG`'s JSON-Schema
 * via the `definition` "Root".
 */
export interface Root {
  /**
   * Discriminator field for root type
   */
  type: 'Root';
  /**
   * Fixed identifier for the root
   */
  id: 'Root';
}

/**
 * Pattern of `Aggregator.id` in the SRG schema.
 */
export const AGGREGATOR_ID_PATTERN = new RegExp("^A\\d+$");

/**
 * Pattern of `Node.id` in the SRG schema.
 */
export const NODE_ID_PATTERN = new RegExp("^(SN(_\\d+|\\d+)|Root)$");
