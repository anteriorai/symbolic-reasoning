/**
 * @anteriorai/srg-parser - Parser for SRG language
 * 
 * Converts .srg source files to typed AST
 */

// Core parsing API
export { 
  parse,
  initParser,
  isParserInitialized
} from './parser.js';

// Types
export type { InitParserOptions } from './parser.js';

// Error types
export { 
  ParseError, 
  SyntaxError, 
  StructuralError, 
  InternalParserError 
} from './parser.js';

// Re-export AST types
export type {
  Position,
  Location,
  CitationReference,
  OutcomeReference,
  SourceFile,
  Definition,
  PolicyContextDefinition,
  PredicateDefinition,
  OutcomeDefinition,
  AggregatorDefinition,
  CitationDefinition,
  CitationRegion,
  Path,
  Expression,
  ReferenceExpression,
  AllExpression,
  AnyExpression,
  NoneExpression,
  AtLeastExpression,
  AtMostExpression,
  ExactlyExpression,
  NotExpression,
} from './ast.js';
