/**
 * Example demonstrating how location information can be used
 * for IDE/LSP features like go-to-definition and error reporting
 */

import { parse } from '../dist/index.js';

const source = `# Healthcare eligibility policy
predicate is_adult: "Is patient 18 or older?"
predicate has_insurance: "Does patient have insurance?"

outcome approved: "Request approved"
outcome denied: "Request denied"

define eligibility: all(is_adult, has_insurance)

eligibility => approved
not(eligibility) => denied`;

async function demonstrateLocationInfo() {
  const ast = await parse(source);

  console.log('=== Location Information Demo ===\n');

  // Example 1: Error reporting with precise locations
  console.log('1. Error Reporting Example:');
  const firstPredicate = ast.definitions[0];
  console.log(`   Predicate "${firstPredicate.id}" defined at:`);
  console.log(`   Line ${firstPredicate.loc.start.line + 1}, Column ${firstPredicate.loc.start.column + 1}`);
  console.log(`   (0-indexed: line ${firstPredicate.loc.start.line}, col ${firstPredicate.loc.start.column})\n`);

  // Example 2: Find all definitions and their locations
  console.log('2. All Definitions with Locations:');
  ast.definitions.forEach((def, i) => {
    const id = def.id || `path_${i}`;
    console.log(`   ${def.type.padEnd(25)} "${id}"`);
    console.log(`     Location: ${def.loc.start.line}:${def.loc.start.column} - ${def.loc.end.line}:${def.loc.end.column}`);
    console.log(`     Offsets: ${def.loc.start.offset} - ${def.loc.end.offset}\n`);
  });

  // Example 3: Expression-level locations for go-to-definition
  console.log('3. Expression Locations (useful for go-to-definition):');
  const aggregator = ast.definitions.find(d => d.type === 'aggregator_definition');
  if (aggregator) {
    console.log(`   Aggregator "${aggregator.id}" expression:`);
    console.log(`     Type: ${aggregator.expression.type}`);
    console.log(`     Location: ${aggregator.expression.loc.start.line}:${aggregator.expression.loc.start.column}`);
    
    if (aggregator.expression.type === 'all' && aggregator.expression.args) {
      console.log(`     Arguments:`);
      aggregator.expression.args.forEach((arg) => {
        if (arg.type === 'reference') {
          console.log(`       - "${arg.id}" at ${arg.loc.start.line}:${arg.loc.start.column}`);
        }
      });
    }
  }
  console.log();

  // Example 4: Simulate go-to-definition
  console.log('4. Go-to-Definition Simulation:');
  console.log('   If user clicks on "is_adult" at line 7, col 33:');
  
  // Find definition of "is_adult"
  const definition = ast.definitions.find(
    d => d.type === 'predicate_definition' && d.id === 'is_adult'
  );
  
  if (definition) {
    console.log(`   Jump to line ${definition.loc.start.line + 1}, column ${definition.loc.start.column + 1}`);
    console.log(`   Definition: ${definition.question}\n`);
  }

  // Example 5: Multi-line ranges
  console.log('5. Multi-line Definition Ranges:');
  ast.definitions.forEach(def => {
    const startLine = def.loc.start.line;
    const endLine = def.loc.end.line;
    if (endLine > startLine) {
      const id = def.id || 'path';
      console.log(`   "${id}" spans ${endLine - startLine + 1} lines (${startLine + 1}-${endLine + 1})`);
    }
  });
}

demonstrateLocationInfo().catch(console.error);


