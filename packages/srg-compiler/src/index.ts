/**
 * @anteriorai/srg-compiler
 * 
 * Compiles SRG syntax (.srg files) into SRG model JSON
 */

import { parse } from '@anteriorai/srg-parser';
import { compile as compileAST } from './compiler.js';

// Export types (SRG model) - from @anteriorai/srg-types package
export * from '@anteriorai/srg-types';

// Re-export AST types from @anteriorai/srg-parser (prefixed to avoid conflicts)
export type {
  SourceFile as ASTSourceFile,
  Definition as ASTDefinition,
  PolicyContextDefinition as ASTPolicyContextDefinition,
  PredicateDefinition as ASTPredicateDefinition,
  OutcomeDefinition as ASTOutcomeDefinition,
  AggregatorDefinition as ASTAggregatorDefinition,
  CitationDefinition as ASTCitationDefinition,
  CitationRegion as ASTCitationRegion,
  Path as ASTPath,
  Expression as ASTExpression,
  ReferenceExpression,
  AllExpression,
  AnyExpression,
  NoneExpression,
  AtLeastExpression,
  AtMostExpression,
  ExactlyExpression,
  NotExpression
} from '@anteriorai/srg-parser';

// Re-export parser and the errors compile() throws, so callers need only this package
export {
  parse,
  ParseError,
  SyntaxError,
  StructuralError,
  InternalParserError
} from '@anteriorai/srg-parser';

// Export compiler
export { compile as compileAST, CompilerError } from './compiler.js';

/**
 * Compile SRG source code into SRG model JSON
 */
export async function compile(source: string) {
  const ast = await parse(source);
  return compileAST(ast);
}

/**
 * Compile an SRG file into SRG model JSON
 */
export async function compileFile(filePath: string) {
  if (typeof process === 'undefined' || !process.versions || !process.versions.node) {
    throw new Error('compileFile is only supported in Node.js environments');
  }
  const fs = await import('fs');
  const bytes = fs.readFileSync(filePath);
  let source: string;
  try {
    // Strict like Python's read_text; keep a BOM as readFileSync(..., 'utf-8') did.
    source = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    throw new Error(`${filePath} is not valid UTF-8`);
  }
  return compile(source);
}
