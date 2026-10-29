#!/usr/bin/env node

/**
 * Generate TypeScript types from the SRG schemas.
 *
 * Usage: npm run generate
 */

import fs from 'node:fs';
import path from 'node:path';
import { compile } from 'json-schema-to-typescript';

const REPO_ROOT = path.join(import.meta.dirname, '..');

const TARGETS = [
  {
    name: '@anteriorai/srg-types package',
    schemaPath: 'schemas/srg-schema-v1.json',
    typeName: 'SRG',
    outputPath: 'packages/srg-types/src/generated/srg.ts',
    idPatterns: true,
    banner: `/**
 * GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * This file is auto-generated from schemas/srg-schema-v1.json
 * To regenerate, run: npm run generate
 *
 * Part of @anteriorai/srg-types package
 */`,
  },
  {
    name: 'SRG AST types',
    schemaPath: 'schemas/srg-ast-v1.json',
    typeName: 'SourceFile',
    outputPath: 'packages/srg-parser/src/generated/ast.ts',
    idPatterns: false,
    banner: `/**
 * GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from schemas/srg-ast-v1.json.
 * To regenerate, run: npm run generate
 */`,
  },
];

// Export the ID formats of aggregators and nodes so code can check IDs against the schema.
function idPatternConstants(schema) {
  const constants = [
    ['AGGREGATOR_ID_PATTERN', 'Aggregator'],
    ['NODE_ID_PATTERN', 'Node'],
  ];
  return constants
    .map(([name, definition]) => {
      const pattern = schema.definitions[definition].properties.id.pattern;
      return `
/**
 * Pattern of \`${definition}.id\` in the SRG schema.
 */
export const ${name} = new RegExp(${JSON.stringify(pattern)});
`;
    })
    .join('');
}

for (const target of TARGETS) {
  const outputPath = path.join(REPO_ROOT, target.outputPath);
  console.log(`📘 Generating ${target.name} at ${target.outputPath}`);

  const schema = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, target.schemaPath), 'utf-8'));
  const types = await compile(schema, target.typeName, {
    bannerComment: target.banner,
    style: {
      semi: true,
      singleQuote: true,
      tabWidth: 2,
    },
    declareExternallyReferenced: true,
    unreachableDefinitions: true,
    enableConstEnums: false,
  });

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, target.idPatterns ? types + idPatternConstants(schema) : types, 'utf-8');
}
