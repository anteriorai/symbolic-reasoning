/**
 * Parser: Converts tree-sitter AST to an internal AST
 */

import { Node } from 'web-tree-sitter';
import * as AST from './ast.js';
import { initParser, isParserInitialized, getParser } from './loader.js';

// Re-export loader functions and types
export { initParser, isParserInitialized } from './loader.js';
export type { InitParserOptions } from './loader.js';

/**
 * Base class for all parsing errors
 */
export class ParseError extends Error {
  constructor(
    message: string,
    public readonly loc?: AST.Location
  ) {
    super(message);
    this.name = 'ParseError';
  }
}

/**
 * Syntax error: tree-sitter detected invalid syntax (ERROR nodes)
 */
export class SyntaxError extends ParseError {
  constructor(message: string, loc: AST.Location) {
    super(message, loc);
    this.name = 'SyntaxError';
  }
}

/**
 * Structural error: missing required fields or malformed structure
 */
export class StructuralError extends ParseError {
  constructor(message: string, loc: AST.Location) {
    super(message, loc);
    this.name = 'StructuralError';
  }
}

/**
 * Internal parser error: indicates a bug in the parser itself
 */
export class InternalParserError extends Error {
  constructor(message: string) {
    super(`Internal parser error: ${message}. Please report this as a bug.`);
    this.name = 'InternalParserError';
  }
}

/**
 * Parse SRG source code into an AST
 * Automatically initializes parser on first call
 * 
 * @param source - SRG source code
 * @returns Parsed AST
 * @throws {ParseError} If source contains syntax or structural errors
 * 
 * @example
 * ```typescript
 * // Simple usage - auto-initialization
 * const ast = await parse('predicate approved {}');
 * 
 * // Explicit initialization with config
 * await initParser({ baseUrl: '/wasm' });
 * const ast = await parse('predicate approved {}');
 * ```
 */
export async function parse(source: string): Promise<AST.SourceFile> {
  // Auto-initialize if needed
  if (!isParserInitialized()) {
    await initParser();
  }
  
  const parser = getParser();
  const tree = parser.parse(source);
  
  if (!tree) {
    throw new InternalParserError('Failed to parse source');
  }

  const root = tree.rootNode;

  // Tree-sitter returns ERROR as the root node when its recovery heuristic
  // can't fit the input into the grammar's start rule at all (e.g. when the
  // input is something like a JSON payload fed to an SRG parser). This is a
  // legitimate user-facing parse failure, not an internal parser bug, so
  // translate it into a SyntaxError pointing at the first unrecoverable
  // token (or the start of input as a fallback).
  if (root.type === 'ERROR') {
    const firstBad = root.firstChild ?? root;
    const loc = getLocation(firstBad);
    throw new SyntaxError(
      `Syntax error at top level at line ${loc.start.line + 1}, column ${loc.start.column + 1}: input is not valid SRG`,
      loc
    );
  }

  const ast = parseSourceFile(root);
  // Preserve contextual errors from AST conversion, then reject any recovery
  // nodes that conversion did not visit (e.g. extra arguments to not()).
  const pending = root.hasError ? [root] : [];
  while (pending.length > 0) {
    const node = pending.pop()!;
    checkForErrorNode(node, 'in source');
    for (const child of node.children) {
      if (child && (child.hasError || child.isMissing)) pending.push(child);
    }
  }
  return ast;
}

function parseSourceFile(node: Node): AST.SourceFile {
  const definitions: AST.Definition[] = [];

  for (const child of node.children) {
    if (!child) continue;
    
    // Skip comments
    if (child.type === 'comment') {
      continue;
    }

    switch (child.type) {
      case 'policy_context_definition': {
        const value = child.childForFieldName('value');
        if (!value) {
          throw new StructuralError('policy_context requires a string', getLocation(child));
        }
        definitions.push({
          type: 'policy_context_definition',
          value: parseStringLiteral(value),
          loc: getLocation(child),
        });
        break;
      }
      case 'predicate_definition':
        definitions.push(parsePredicateDefinition(child));
        break;
      case 'outcome_definition':
        definitions.push(parseOutcomeDefinition(child));
        break;
      case 'aggregator_definition':
        definitions.push(parseAggregatorDefinition(child));
        break;
      case 'citation_definition':
        definitions.push(parseCitationDefinition(child));
        break;
      case 'path':
        definitions.push(parsePath(child));
        break;
      case 'ERROR':
        // Report syntax errors at top level with location information
        checkForErrorNode(child, 'at top level');
        break;
      default:
        throw new StructuralError(
          `Unknown definition type: ${child.type}`,
          getLocation(child)
        );
    }
  }

  return { type: 'source_file', definitions };
}

/**
 * Interface for common properties that can be attached to any component
 */
interface CommonProperties {
  label?: string;
  doc?: string;
  citation_refs?: AST.CitationReference[];
  properties?: Record<string, unknown>;
}

/**
 * Parse common properties from node children
 * Validates for duplicates and returns structured properties
 */
function parseCommonProperties(node: Node): CommonProperties {
  const result: CommonProperties = {};
  const seenProperties = new Set<string>();
  
  for (const child of node.children) {
    if (!child) continue;
    
    switch (child.type) {
      case 'label_property': {
        if (seenProperties.has('label')) {
          throw new StructuralError(`Duplicate 'label' property found`, getLocation(child.firstChild!));
        }
        seenProperties.add('label');
        const valueNode = child.childForFieldName('value');
        if (valueNode) {
          result.label = parseStringLiteral(valueNode);
        }
        break;
      }
      
      case 'doc_property': {
        if (seenProperties.has('doc')) {
          throw new StructuralError(`Duplicate 'doc' property found`, getLocation(child.firstChild!));
        }
        seenProperties.add('doc');
        const valueNode = child.childForFieldName('value');
        if (valueNode) {
          result.doc = parseStringLiteral(valueNode);
        }
        break;
      }
      
      case 'cite_property': {
        if (seenProperties.has('cite')) {
          throw new StructuralError(`Duplicate 'cite' property found`, getLocation(child.firstChild!));
        }
        seenProperties.add('cite');
        
        result.citation_refs = [];
        
        // Check if it's a single citation or an array
        const citationNode = child.childForFieldName('citation');
        if (citationNode && citationNode.type === 'identifier') {
          // Single citation: cite: id
          result.citation_refs.push({
            id: citationNode.text,
            loc: getLocation(citationNode)
          });
        } else {
          // Array citation: cite: [id1, id2, ...]
          const arrayNode = child.children.find(c => c && c.type === 'citation_array');
          if (arrayNode) {
            for (const arrayChild of arrayNode.children) {
              if (arrayChild && arrayChild.type === 'identifier') {
                result.citation_refs.push({
                  id: arrayChild.text,
                  loc: getLocation(arrayChild)
                });
              }
            }
          }
        }
        break;
      }
      
      case 'metadata_property': {
        if (seenProperties.has('metadata')) {
          throw new StructuralError(`Duplicate 'metadata' property found`, getLocation(child.firstChild!));
        }
        seenProperties.add('metadata');
        const propertyBlock = child.children.find(
          (c) => c && c.type === 'property_block'
        );
        if (propertyBlock) {
          result.properties = parsePropertyBlock(propertyBlock);
        }
        break;
      }
    }
  }
  
  return result;
}

function parsePredicateDefinition(
  node: Node
): AST.PredicateDefinition {
  // Check for syntax errors first
  for (const child of node.children) {
    checkForErrorNode(child, 'in predicate definition');
  }

  const idNode = node.childForFieldName('id');
  const questionNode = node.childForFieldName('question');

  // Defensive checks: these should not occur with a correct grammar,
  // but protect against future grammar changes or internal parser bugs
  if (!idNode) {
    throw new StructuralError(
      'Predicate definition missing id',
      getLocation(node)
    );
  }

  if (!questionNode) {
    throw new StructuralError(
      'Predicate definition missing question',
      getLocation(node)
    );
  }

  const id = idNode.text;
  const question = parseStringLiteral(questionNode);

  // Parse common properties
  const commonProps = parseCommonProperties(node);

  // Parse context (predicate-specific property)
  let context: string | undefined;
  const seenContext = new Set<string>();
  for (const child of node.children) {
    if (child && child.type === 'context_property') {
      if (seenContext.has('context')) {
        throw new StructuralError(`Duplicate 'context' property found`, getLocation(child.firstChild!));
      }
      seenContext.add('context');
      const valueNode = child.childForFieldName('value');
      if (valueNode) {
        context = parseStringLiteral(valueNode);
      }
    }
  }

  return {
    type: 'predicate_definition',
    id,
    question,
    ...commonProps,
    ...(context !== undefined && { context }),
    loc: getLocation(node)
  };
}

function parseOutcomeDefinition(
  node: Node
): AST.OutcomeDefinition {
  for (const child of node.children) {
    checkForErrorNode(child, 'in outcome definition');
  }

  const idNode = node.childForFieldName('id');
  const descriptionNode = node.childForFieldName('description');

  // Defensive checks: these should not occur with a correct grammar,
  // but protect against future grammar changes or internal parser bugs
  if (!idNode) {
    throw new StructuralError(
      'Outcome definition missing id',
      getLocation(node)
    );
  }

  if (!descriptionNode) {
    throw new StructuralError(
      'Outcome definition missing description',
      getLocation(node)
    );
  }

  const id = idNode.text;
  const description = parseStringLiteral(descriptionNode);  // Primary inline value

  // Parse common properties
  const commonProps = parseCommonProperties(node);

  return {
    type: 'outcome_definition',
    id,
    description,
    ...commonProps,
    loc: getLocation(node)
  };
}

function parseAggregatorDefinition(
  node: Node
): AST.AggregatorDefinition {
  for (const child of node.children) {
    checkForErrorNode(child, 'in aggregator definition');
  }

  const idNode = node.childForFieldName('id');
  const exprNode = node.childForFieldName('expression');

  // Defensive checks: these should not occur with a correct grammar,
  // but protect against future grammar changes or internal parser bugs
  if (!idNode) {
    throw new StructuralError(
      'Aggregator definition missing id',
      getLocation(node)
    );
  }

  if (!exprNode) {
    throw new StructuralError(
      'Aggregator definition missing expression',
      getLocation(node)
    );
  }

  const id = idNode.text;
  const expression = parseExpression(exprNode);

  // Parse common properties
  const commonProps = parseCommonProperties(node);

  return {
    type: 'aggregator_definition',
    id,
    expression,
    ...commonProps,
    loc: getLocation(node)
  };
}

function parseCitationDefinition(
  node: Node
): AST.CitationDefinition {

  for (const child of node.children) {
    checkForErrorNode(child, 'in citation definition');
  }

  const idNode = node.childForFieldName('id');

  if (!idNode) {
    throw new StructuralError('Citation definition missing id',
      getLocation(node)
    );
  }

  const id = idNode.text;

  // Parse property block (required for citations)
  const propertyBlock = node.children.find(
    (child) => child && child.type === 'property_block'
  );
  
  if (!propertyBlock) {
    throw new StructuralError('Citation definition missing property block',
      getLocation(node)
    );
  }

  const properties = parsePropertyBlock(propertyBlock);

  // Extract and validate required fields
  if (!properties.source_ref || typeof properties.source_ref !== 'string') {
    throw new StructuralError(`Citation '${id}' missing required field: source_ref`,
      getLocation(node)
    );
  }

  const citation: AST.CitationDefinition = {
    type: 'citation_definition',
    id,
    source_ref: properties.source_ref,
    loc: getLocation(node)
  };

  // Parse optional regions array
  if (properties.regions !== undefined) {
    if (!Array.isArray(properties.regions)) {
      throw new StructuralError(`Citation '${id}': regions must be an array`,
        getLocation(node)
      );
    }
    
    citation.regions = properties.regions.map((region: any, index: number) => {
      if (typeof region !== 'object' || region === null) {
        throw new StructuralError(`Citation '${id}': region ${index} must be an object`,
          getLocation(node)
        );
      }
      
      if (!Number.isInteger(region.page) || region.page < 0) {
        throw new StructuralError(`Citation '${id}': region ${index} missing required field: page`,
          getLocation(node)
        );
      }
      
      if (!Array.isArray(region.box) || region.box.length !== 4) {
        throw new StructuralError(`Citation '${id}': region ${index} box must be an array of 4 vertices`,
          getLocation(node)
        );
      }
      
      // Validate that each vertex is a coordinate pair [x, y]
      if (!region.box.every((vertex: any) => 
        Array.isArray(vertex) && 
        vertex.length === 2 && 
        typeof vertex[0] === 'number' && 
        typeof vertex[1] === 'number'
      )) {
        throw new StructuralError(`Citation '${id}': region ${index} box must contain 4 coordinate pairs [[x, y], ...]`,
          getLocation(node)
        );
      }
      
      return {
        page: region.page,
        box: region.box as [[number, number], [number, number], [number, number], [number, number]],
      };
    });
  }

  // Parse optional filename field
  if (properties.filename && typeof properties.filename === 'string') {
    citation.filename = properties.filename;
  }

  // Parse optional excerpt field
  if (properties.excerpt && typeof properties.excerpt === 'string') {
    citation.excerpt = properties.excerpt;
  }

  // Store any other properties as metadata
  const knownFields = ['source_ref', 'filename', 'regions', 'excerpt'];
  const metadataFields = Object.keys(properties).filter(key => !knownFields.includes(key));
  
  if (metadataFields.length > 0) {
    citation.metadata = {};
    for (const key of metadataFields) {
      citation.metadata[key] = properties[key];
    }
  }

  return citation;
}

function parsePath(node: Node): AST.Path {
  const idNode = node.childForFieldName('id');
  const outcomeNode = node.childForFieldName('outcome');
  
  // Defensive checks: these should not occur with a correct grammar,
  // but protect against future grammar changes or internal parser bugs
  if (!idNode) {
    throw new StructuralError(
      'Path missing id',
      getLocation(node)
    );
  }

  if (!outcomeNode) {
    throw new StructuralError(
      'Path missing outcome',
      getLocation(node)
    );
  }

  const id = idNode.text;

  // Collect all 'step' fields (chained expressions)
  const steps: AST.Expression[] = [];
  const conditions: boolean[] = [];
  
  for (const child of node.children) {
    if (!child) continue;
    
    // Check for syntax errors in path
    checkForErrorNode(child, 'in path');
    
    if (child.type === 'expression') {
      // This is a step in the chain
      steps.push(parseExpression(child));
    } else if (child.text === '=>' || child.text === '!=>') {
      conditions.push(child.text === '=>');
    }
  }

  if (steps.length === 0) {
    throw new StructuralError(
      'Path has no steps/conditions',
      getLocation(node)
    );
  }

  const outcome_ref: AST.OutcomeReference = {
    id: outcomeNode.text,
    loc: getLocation(outcomeNode)
  };

  // Parse common properties
  const commonProps = parseCommonProperties(node);

  return {
    type: 'path',
    id,
    steps,
    ...(conditions.some(condition => !condition) && { conditions: conditions as [boolean, ...boolean[]] }),
    outcome_ref,
    ...commonProps,
    loc: getLocation(node)
  };
}

function parseExpression(node: Node): AST.Expression {
  // Unwrap 'expression' wrapper nodes
  const actualNode = node.type === 'expression' ? node.children[0] : node;
  
  if (!actualNode) {
    throw new StructuralError(
      'Expression node is empty',
      getLocation(node)
    );
  }

  // Check for syntax errors
  checkForErrorNode(actualNode, 'in expression');
  
  const loc = getLocation(actualNode);

  // Helper to parse argument list from an expression node
  const parseArgs = (exprNode: Node): AST.Expression[] => {
    const argListNode = exprNode.children.find(
      (child) => child && child.type === 'argument_list'
    );

    if (!argListNode) {
      return [];
    }

    // Check for ERROR nodes that are siblings to argument_list (e.g., ", @invalid" in "all(p1, @invalid)")
    for (const sibling of exprNode.children) {
      if (sibling && sibling !== argListNode && sibling.type === 'ERROR') {
        checkForErrorNode(sibling, 'in argument list');
      }
    }

    // Parse arguments from within argument_list
    const args: AST.Expression[] = [];
    for (const child of argListNode.children) {
      if (!child) continue;
      if (child.type === 'expression') {
        args.push(parseExpression(child));
      }
    }
    return args;
  };

  switch (actualNode.type) {
    case 'reference': {
      const idNode = actualNode.childForFieldName('id') || actualNode.children[0];
      if (!idNode || !idNode.text) {
        throw new StructuralError(
          'Reference missing identifier',
          loc
        );
      }
      return { type: 'reference', id: idNode.text, loc };
    }

    // Simple aggregators: all(), any(), none()
    case 'all_expression':
    case 'any_expression':
    case 'none_expression': {
      const args = parseArgs(actualNode);
      if (args.length === 0) {
        const expressionType = actualNode.type.replace('_expression', '');
        throw new StructuralError(
          `${expressionType} expression requires at least one argument`,
          loc
        );
      }
      const type = actualNode.type.replace('_expression', '') as 'all' | 'any' | 'none';
      return { type, args, loc };
    }

    // Counted aggregators: atleast(n, ...), atmost(n, ...), exactly(n, ...)
    case 'atleast_expression':
    case 'atmost_expression':
    case 'exactly_expression': {
      const countNode = actualNode.childForFieldName('count');
      if (!countNode) {
        const exprType = actualNode.type.replace('_expression', '');
        throw new StructuralError(
          `${exprType} expression missing count`,
          loc
        );
      }
      const count = parseInt(countNode.text, 10);
      const args = parseArgs(actualNode);
      const type = actualNode.type.replace('_expression', '') as 'atleast' | 'atmost' | 'exactly';
      if (type === 'atleast' && count < 1) {
        throw new StructuralError('atleast count must be at least 1', loc);
      }
      if ((type === 'atmost' || type === 'exactly') && count < 0) {
        throw new StructuralError(`${type} count must be non-negative`, loc);
      }
      return { type, count, args, loc };
    }

    // Unary negation: not(expr)
    case 'not_expression': {
      const exprNode = actualNode.childForFieldName('expr');
      if (!exprNode) {
        throw new StructuralError(
          'not expression missing expr',
          loc
        );
      }
      const expr = parseExpression(exprNode);
      return { type: 'not', expr, loc };
    }

    default:
      throw new StructuralError(
        `Unknown expression type: ${actualNode.type}`,
        getLocation(actualNode)
      );
  }
}

function parseStringLiteral(node: Node): string {
  const text = node.text;

  // Handle triple-quoted strings
  if (text.startsWith('"""') && text.endsWith('"""')) {
    return text.slice(3, -3).trim();
  }

  // Handle regular strings
  if (text.startsWith('"') && text.endsWith('"')) {
    return JSON.parse(text); // Use JSON.parse to handle escape sequences
  }

  throw new StructuralError(
    `Invalid string literal: ${text}`,
    getLocation(node)
  );
}

function parsePropertyBlock(node: Node): Record<string, unknown> {
  const props: Record<string, unknown> = {};

  for (const child of node.children) {
    if (!child) continue;
    
    // Check for syntax errors in property block
    checkForErrorNode(child, 'in property block');
    
    if (child.type === 'property') {
      const keyNode = child.childForFieldName('key');
      const valueNode = child.childForFieldName('value');

      if (keyNode && valueNode) {
        props[keyNode.text] = parsePropertyValue(valueNode);
      }
    }
  }

  return props;
}

function parsePropertyValue(node: Node): unknown {
  // Handle property_value wrapper nodes
  const actualNode = node.type === 'property_value' ? node.children[0] : node;

  if (!actualNode) {
    throw new StructuralError(
      'Property value is empty',
      getLocation(node)
    );
  }

  switch (actualNode.type) {
    case 'string':
      return parseStringLiteral(actualNode);
    case 'number':
      return actualNode.text.includes('.')
        ? parseFloat(actualNode.text)
        : parseInt(actualNode.text, 10);
    case 'boolean':
      return actualNode.text === 'true';
    case 'property_array':
      return parsePropertyArray(actualNode);
    case 'property_object':
      return parsePropertyObject(actualNode);
    default:
      throw new StructuralError(
        `Unknown property value type: ${actualNode.type}`,
        getLocation(actualNode)
      );
  }
}

function parsePropertyArray(node: Node): unknown[] {
  const items: unknown[] = [];

  for (const child of node.children) {
    if (!child) continue;
    
    // Check for syntax errors in property array
    checkForErrorNode(child, 'in property array');
    
    if (child.type === 'property_value') {
      items.push(parsePropertyValue(child));
    }
  }

  return items;
}

function parsePropertyObject(node: Node): Record<string, unknown> {
  const obj: Record<string, unknown> = {};

  for (const child of node.children) {
    if (!child) continue;
    
    // Check for syntax errors in property object
    checkForErrorNode(child, 'in property object');
    
    if (child.type === 'property') {
      const keyNode = child.childForFieldName('key');
      const valueNode = child.childForFieldName('value');

      if (keyNode && valueNode) {
        obj[keyNode.text] = parsePropertyValue(valueNode);
      }
    }
  }

  return obj;
}

/**
 * Reject ERROR nodes and tokens inserted by syntax error recovery.
 */
function checkForErrorNode(
  node: Node | null | undefined,
  context: string
): void {
  if (!node || (node.type !== 'ERROR' && !node.isMissing)) {
    return;
  }

  const loc = getLocation(node);
  const text = node.text || '<unknown>';
  throw new SyntaxError(
    `Syntax error ${context} at line ${loc.start.line + 1}, column ${loc.start.column + 1}: unexpected token "${text}"`,
    loc
  );
}

function getLocation(node: Node): AST.Location {
  return {
    start: {
      line: node.startPosition.row,
      column: node.startPosition.column,
      offset: node.startIndex
    },
    end: {
      line: node.endPosition.row,
      column: node.endPosition.column,
      offset: node.endIndex
    }
  };
}
