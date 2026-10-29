#!/usr/bin/env node

/**
 * CLI tool for compiling SRG files
 */

import { compileFile } from './index.js';
import * as fs from 'fs';
import * as path from 'path';

const args = process.argv.slice(2);

if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
  console.log(`
Usage: srg-compile <file.srg> [options]

Options:
  --output, -o <file>    Output file path (default: <input>.json)
  --pretty, -p           Pretty print JSON output
  --help, -h             Show this help

Examples:
  srg-compile policy.srg
  srg-compile policy.srg --output out.json --pretty
`);
  process.exit(args.length === 0 ? 1 : 0);
}

const inputFile = args[0];
let outputFile: string | null = null;
let pretty = false;

for (let i = 1; i < args.length; i++) {
  const arg = args[i];
  if (arg === '--output' || arg === '-o') {
    outputFile = args[++i];
  } else if (arg === '--pretty' || arg === '-p') {
    pretty = true;
  }
}

if (!outputFile) {
  outputFile = `${inputFile}.json`;
}

console.log(`📖 Compiling: ${inputFile}`);
console.log(`📝 Output: ${outputFile}`);
console.log('─'.repeat(60));

try {
  if (!fs.existsSync(inputFile)) {
    throw new Error(`Input file not found: ${inputFile}`);
  }

  const result = await compileFile(inputFile);

  const json = pretty ? JSON.stringify(result, null, 2) : JSON.stringify(result);
  if (fs.existsSync(outputFile)) {
    const input = fs.statSync(inputFile, { bigint: true });
    const output = fs.statSync(outputFile, { bigint: true });
    if (input.ino === output.ino && input.dev === output.dev) {
      throw new Error(`Output path is the input file: ${inputFile}`);
    }
  }
  fs.writeFileSync(outputFile, json);

  console.log(`\n✅ Success!\n`);
  console.log(`📊 Summary:`);
  console.log(`   Predicates:  ${Object.keys(result.predicates).length}`);
  console.log(`   Outcomes:    ${Object.keys(result.outcomes).length}`);
  console.log(`   Aggregators: ${Object.keys(result.aggregators).length}`);
  console.log(`   Nodes:       ${Object.keys(result.nodes).length}`);
  console.log(`   Edges:       ${Object.keys(result.edges).length}`);
  console.log(`\n💾 Saved to: ${outputFile}`);

  if (pretty) {
    console.log(`\n📋 Preview:`);
    const preview = JSON.stringify(result, null, 2);
    const lines = preview.split('\n');
    if (lines.length > 30) {
      console.log(lines.slice(0, 15).join('\n'));
      console.log(`   ... (${lines.length - 30} more lines) ...`);
      console.log(lines.slice(-15).join('\n'));
    } else {
      console.log(preview);
    }
  }

} catch (error: any) {
  console.error(`\n❌ Error: ${error.message}`);
  if (error.stack) {
    console.error('\nStack trace:');
    console.error(error.stack);
  }
  process.exit(1);
}
