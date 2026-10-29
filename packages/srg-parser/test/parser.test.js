import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { parse, ParseError, SyntaxError, StructuralError, InternalParserError } from '../dist/index.js';

describe('SRG Parser', () => {
  describe('Policy Context', () => {
    it('should parse policy context separately from predicate context', async () => {
      const ast = await parse(`
policy_context: "Underwriting é🙂"
predicate p: "Question"
  context: "Check date of birth"
`);
      assert.equal(ast.definitions.length, 2);
      assert.equal(ast.definitions[0].type, 'policy_context_definition');
      assert.equal(ast.definitions[0].value, 'Underwriting é🙂');
      assert.deepEqual(ast.definitions[0].loc.start, { line: 1, column: 0, offset: 1 });
      assert.deepEqual(ast.definitions[0].loc.end, { line: 1, column: 34, offset: 35 });
      assert.equal(ast.definitions[1].context, 'Check date of birth');
    });

    it('should allow policy context after other definitions', async () => {
      const ast = await parse(`
predicate p: "Question"
policy_context: "Policy"
outcome o: "Outcome"
`);
      assert.equal(ast.definitions.length, 3);
      assert.deepEqual(ast.definitions.map(def => def.type), [
        'predicate_definition', 'policy_context_definition', 'outcome_definition',
      ]);
      assert.equal(ast.definitions[1].value, 'Policy');
    });

    it('should use the existing multiline string rules', async () => {
      const ast = await parse(`policy_context: """
Use the 2026 policy.
Apply it to the application date.
"""`);
      assert.equal(ast.definitions[0].value, 'Use the 2026 policy.\nApply it to the application date.');
    });

    it('should preserve an explicitly empty context', async () => {
      assert.equal((await parse('policy_context: ""')).definitions[0].value, '');
    });

    it('should leave policy context absent when omitted', async () => {
      assert.deepEqual((await parse('predicate p: "Question"')).definitions.map(def => def.type), ['predicate_definition']);
    });

    it('should preserve duplicate declarations for compiler validation', async () => {
      const ast = await parse('policy_context: ""\npolicy_context: "second"');
      assert.deepEqual(ast.definitions.map(def => def.value), ['', 'second']);
      assert.equal(ast.definitions[1].loc.start.line, 1);
    });

    it('should require a string value', async () => {
      await assert.rejects(() => parse('policy_context: 42'), ParseError);
    });

    it('should require a colon', async () => {
      await assert.rejects(() => parse('policy_context "Policy"'), ParseError);
    });

    it('should reject a missing value', async () => {
      await assert.rejects(() => parse('policy_context:'), ParseError);
    });
  });

  describe('Predicate Definitions', () => {
    it('should parse a simple predicate', async () => {
      const source = 'predicate is_adult: "Is the patient 18 or older?"';
      const ast = await parse(source);

      assert.equal(ast.type, 'source_file');
      assert.equal(ast.definitions.length, 1);
      assert.equal(ast.definitions[0].type, 'predicate_definition');
      assert.equal(ast.definitions[0].id, 'is_adult');
      assert.equal(ast.definitions[0].question, 'Is the patient 18 or older?');
      assert.equal(ast.definitions[0].properties, undefined);
    });

    it('should parse a predicate with properties', async () => {
      const source = `
        predicate is_adult: "Is the patient 18 or older?"
          context: "Check birth date"
          metadata: {
            priority: 1,
            required: true
          }
      `;
      const ast = await parse(source);

      const pred = ast.definitions[0];
      assert.equal(pred.type, 'predicate_definition');
      assert.equal(pred.id, 'is_adult');
      assert.equal(pred.context, 'Check birth date');
      assert.deepEqual(pred.properties, {
        priority: 1,
        required: true
      });
    });

    it('should parse triple-quoted strings', async () => {
      const source = `
        predicate complex: """
          This is a multi-line
          question with details
        """
      `;
      const ast = await parse(source);

      const pred = ast.definitions[0];
      assert.equal(pred.type, 'predicate_definition');
      assert.equal(pred.question, 'This is a multi-line\n          question with details');
    });
  });

  describe('Outcome Definitions', () => {
    it('should parse a simple outcome', async () => {
      const source = 'outcome approved: "Request approved"';
      const ast = await parse(source);

      assert.equal(ast.definitions.length, 1);
      assert.equal(ast.definitions[0].type, 'outcome_definition');
      assert.equal(ast.definitions[0].id, 'approved');
      assert.equal(ast.definitions[0].description, 'Request approved');
    });

    it('should parse an outcome with properties', async () => {
      const source = `
        outcome approved: "Request approved"
          metadata: {
            notification_required: true,
            approval_level: "automatic"
          }
      `;
      const ast = await parse(source);

      const outcome = ast.definitions[0];
      assert.equal(outcome.type, 'outcome_definition');
      assert.deepEqual(outcome.properties, {
        notification_required: true,
        approval_level: 'automatic'
      });
    });
  });

  describe('Aggregator Definitions', () => {
    it('should parse aggregator with all()', async () => {
      const source = `
        predicate p1: "P1"
        predicate p2: "P2"
        define check: all(p1, p2)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[2];
      assert.equal(agg.type, 'aggregator_definition');
      assert.equal(agg.id, 'check');
      assert.equal(agg.expression.type, 'all');
      assert.equal(agg.expression.args.length, 2);
      assert.equal(agg.expression.args[0].type, 'reference');
      assert.equal(agg.expression.args[0].id, 'p1');
    });

    it('should parse aggregator with any()', async () => {
      const source = `
        predicate p1: "P1"
        define check: any(p1)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.expression.type, 'any');
      assert.equal(agg.expression.args.length, 1);
    });

    it('should parse aggregator with none()', async () => {
      const source = `
        predicate p1: "P1"
        define check: none(p1)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.expression.type, 'none');
    });

    it('should parse aggregator with not()', async () => {
      const source = `
        predicate p1: "P1"
        define check: not(p1)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.expression.type, 'not');
      assert.equal(agg.expression.expr.type, 'reference');
      assert.equal(agg.expression.expr.id, 'p1');
    });

    it('should parse aggregator with atleast()', async () => {
      const source = `
        predicate p1: "P1"
        predicate p2: "P2"
        define check: atleast(1, p1, p2)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[2];
      assert.equal(agg.expression.type, 'atleast');
      assert.equal(agg.expression.count, 1);
      assert.equal(agg.expression.args.length, 2);
    });

    it('should parse aggregator with atmost()', async () => {
      const source = `
        predicate p1: "P1"
        define check: atmost(2, p1)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.expression.type, 'atmost');
      assert.equal(agg.expression.count, 2);
    });

    it('should parse aggregator with exactly()', async () => {
      const source = `
        predicate p1: "P1"
        define check: exactly(3, p1)
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.expression.type, 'exactly');
      assert.equal(agg.expression.count, 3);
    });

    it('should parse nested aggregators', async () => {
      const source = `
        predicate p1: "P1"
        predicate p2: "P2"
        define check: all(p1, any(p2))
      `;
      const ast = await parse(source);

      const agg = ast.definitions[2];
      assert.equal(agg.expression.type, 'all');
      assert.equal(agg.expression.args[0].type, 'reference');
      assert.equal(agg.expression.args[1].type, 'any');
      assert.equal(agg.expression.args[1].args[0].id, 'p2');
    });
  });

  describe('Path Definitions', () => {
    it('should parse a simple path', async () => {
      const source = `
        predicate p1: "P1"
        outcome approved: "Approved"
        path test_path: p1 => approved
      `;
      const ast = await parse(source);

      const path = ast.definitions[2];
      assert.equal(path.type, 'path');
      assert.equal(path.steps.length, 1);
      assert.equal(path.steps[0].type, 'reference');
      assert.equal(path.steps[0].id, 'p1');
      assert.equal(path.outcome_ref.id, 'approved');
    });

    it('should parse a path with all()', async () => {
      const source = `
        predicate p1: "P1"
        predicate p2: "P2"
        outcome approved: "Approved"
        path test_path: all(p1, p2) => approved
      `;
      const ast = await parse(source);

      const path = ast.definitions[3];
      assert.equal(path.type, 'path');
      assert.equal(path.steps[0].type, 'all');
      assert.equal(path.steps[0].args.length, 2);
    });

    it('should parse chained paths', async () => {
      const source = `
        predicate p1: "P1"
        predicate p2: "P2"
        define agg: all(p1, p2)
        outcome approved: "Approved"
        path test_path: root => agg => approved
      `;
      const ast = await parse(source);

      const path = ast.definitions[4];
      assert.equal(path.type, 'path');
      assert.equal(path.steps.length, 2);
      assert.equal(path.steps[0].type, 'reference');
      assert.equal(path.steps[0].id, 'root');
      assert.equal(path.steps[1].type, 'reference');
      assert.equal(path.steps[1].id, 'agg');
      assert.equal(path.outcome_ref.id, 'approved');
    });
  });

  describe('Property Blocks', () => {
    it('should parse string properties', async () => {
      const source = `
        predicate p: "P"
          metadata: {
            text: "hello world"
          }
      `;
      const ast = await parse(source);

      assert.equal(ast.definitions[0].properties.text, 'hello world');
    });

    it('should parse number properties', async () => {
      const source = `
        predicate p: "P"
          metadata: {
            integer: 42,
            float: 3.14
          }
      `;
      const ast = await parse(source);

      const props = ast.definitions[0].properties;
      assert.equal(props.integer, 42);
      assert.equal(props.float, 3.14);
    });

    it('should parse boolean properties', async () => {
      const source = `
        predicate p: "P"
          metadata: {
            enabled: true,
            disabled: false
          }
      `;
      const ast = await parse(source);

      const props = ast.definitions[0].properties;
      assert.equal(props.enabled, true);
      assert.equal(props.disabled, false);
    });

    it('should parse array properties', async () => {
      const source = `
        predicate p: "P"
          metadata: {
            tags: ["critical", "urgent"],
            numbers: [1, 2, 3]
          }
      `;
      const ast = await parse(source);

      const props = ast.definitions[0].properties;
      assert.deepEqual(props.tags, ['critical', 'urgent']);
      assert.deepEqual(props.numbers, [1, 2, 3]);
    });

    it('should parse nested object properties', async () => {
      const source = `
        predicate p: "P"
          metadata: {
            config: {
              author: "John",
              version: 2,
              active: true
            }
          }
      `;
      const ast = await parse(source);

      const props = ast.definitions[0].properties;
      assert.deepEqual(props.config, {
        author: 'John',
        version: 2,
        active: true
      });
    });

    it('should parse deeply nested properties', async () => {
      const source = `
        predicate p: "P"
          metadata: {
            config: {
              source: {
                document: "policy.pdf",
                page: 23
              },
              confidence: 0.98
            }
          }
      `;
      const ast = await parse(source);

      const props = ast.definitions[0].properties;
      assert.deepEqual(props.config, {
        source: {
          document: 'policy.pdf',
          page: 23
        },
        confidence: 0.98
      });
    });
  });

  describe('Comments and Whitespace', () => {
    for (const declaration of [
      'predicate p: "Question"',
      'outcome o: "Outcome"',
      'define a: all(p)',
      'path decision: p => o',
    ]) {
      for (const separator of [' # inline comment\n', '\n# standalone comment\n']) {
        it(`should retain properties after comments in ${declaration}`, async () => {
          const source = `${declaration}${separator}  label: "Label"${separator}  doc: "Documentation"`;
          const ast = await parse(source);
          assert.equal(ast.definitions.length, 1);
          const definition = ast.definitions[0];
          assert.equal(definition.label, 'Label');
          assert.equal(definition.doc, 'Documentation');
          assert.deepEqual(definition.loc, {
            start: { line: 0, column: 0, offset: 0 },
            end: {
              line: source.split('\n').length - 1,
              column: '  doc: "Documentation"'.length,
              offset: source.length,
            },
          });
        });
      }
    }

    it('should skip comments', async () => {
      const source = `
        # This is a comment
        predicate p1: "P1"
        # Another comment
        outcome approved: "Approved"
      `;
      const ast = await parse(source);

      assert.equal(ast.definitions.length, 2);
      assert.equal(ast.definitions[0].type, 'predicate_definition');
      assert.equal(ast.definitions[1].type, 'outcome_definition');
    });

    it('should handle multiple blank lines', async () => {
      const source = `
        predicate p1: "P1"


        predicate p2: "P2"
      `;
      const ast = await parse(source);

      assert.equal(ast.definitions.length, 2);
    });
  });

  describe('Complex Scenarios', () => {
    it('should parse a complete policy', async () => {
      const source = `
        # Healthcare policy
        predicate is_adult: "Is patient 18+?"
          context: "Check DOB"
        
        predicate has_insurance: "Has insurance?"
        
        outcome approved: "Approved"
          metadata: {
            notification: true
          }
        
        outcome denied: "Denied"
        
        define eligibility: all(is_adult, has_insurance)
        
        path approval_path: eligibility => approved
        path denial_path: not(eligibility) => denied
      `;
      const ast = await parse(source);

      assert.equal(ast.definitions.length, 7);
      
      // Verify predicates
      assert.equal(ast.definitions[0].type, 'predicate_definition');
      assert.equal(ast.definitions[0].id, 'is_adult');
      assert.equal(ast.definitions[0].context, 'Check DOB');
      
      assert.equal(ast.definitions[1].type, 'predicate_definition');
      assert.equal(ast.definitions[1].id, 'has_insurance');
      
      // Verify outcomes
      assert.equal(ast.definitions[2].type, 'outcome_definition');
      assert.equal(ast.definitions[3].type, 'outcome_definition');
      
      // Verify aggregator
      assert.equal(ast.definitions[4].type, 'aggregator_definition');
      assert.equal(ast.definitions[4].expression.type, 'all');
      
      // Verify paths
      assert.equal(ast.definitions[5].type, 'path');
      assert.equal(ast.definitions[6].type, 'path');
    });

    it('should parse aggregators with properties', async () => {
      const source = `
        predicate p1: "P1"
        define check: all(p1)
          doc: "Combined check"
          metadata: {
            version: 2
          }
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.type, 'aggregator_definition');
      assert.equal(agg.doc, 'Combined check');
      assert.deepEqual(agg.properties, {
        version: 2
      });
    });
  });

  describe('Location Information', () => {
    it('should track precise locations for multi-line policy with nested expressions', async () => {
      const source = `predicate is_adult: "Is patient 18+"
predicate has_insurance: "Has insurance?"
outcome approved: "Approved"
define eligibility: all(is_adult, has_insurance)
path p: eligibility => approved`;

      const ast = await parse(source);

      // Helper to extract text using location
      const extractText = (loc) => source.substring(loc.start.offset, loc.end.offset);

      // Test predicate locations and extract exact text
      const pred1 = ast.definitions[0];
      assert.equal(pred1.type, 'predicate_definition');
      assert.equal(pred1.id, 'is_adult');
      assert.equal(pred1.loc.start.line, 0);
      assert.equal(pred1.loc.start.column, 0);
      assert.equal(extractText(pred1.loc), 'predicate is_adult: "Is patient 18+"');

      const pred2 = ast.definitions[1];
      assert.equal(pred2.id, 'has_insurance');
      assert.equal(pred2.loc.start.line, 1);
      assert.equal(extractText(pred2.loc), 'predicate has_insurance: "Has insurance?"');

      // Test outcome location
      const outcome = ast.definitions[2];
      assert.equal(outcome.type, 'outcome_definition');
      assert.equal(outcome.loc.start.line, 2);
      assert.equal(extractText(outcome.loc), 'outcome approved: "Approved"');

      // Test aggregator with nested expressions
      const agg = ast.definitions[3];
      assert.equal(agg.type, 'aggregator_definition');
      assert.equal(agg.id, 'eligibility');
      assert.equal(agg.loc.start.line, 3);
      assert.equal(extractText(agg.loc), 'define eligibility: all(is_adult, has_insurance)');

      // Test nested expression locations
      const allExpr = agg.expression;
      assert.equal(allExpr.type, 'all');
      assert.equal(extractText(allExpr.loc), 'all(is_adult, has_insurance)');

      // Test individual reference locations within expression
      const ref1 = allExpr.args[0];
      assert.equal(ref1.type, 'reference');
      assert.equal(ref1.id, 'is_adult');
      assert.equal(extractText(ref1.loc), 'is_adult');

      const ref2 = allExpr.args[1];
      assert.equal(ref2.type, 'reference');
      assert.equal(ref2.id, 'has_insurance');
      assert.equal(extractText(ref2.loc), 'has_insurance');

      // Test path location
      const path = ast.definitions[4];
      assert.equal(path.type, 'path');
      assert.equal(path.loc.start.line, 4);
      assert.equal(extractText(path.loc), 'path p: eligibility => approved');

      // Verify path step location (the reference to eligibility)
      const pathStep = path.steps[0];
      assert.equal(pathStep.type, 'reference');
      assert.equal(extractText(pathStep.loc), 'eligibility');
    });

    it('should accurately locate deeply nested expressions', async () => {
      const source = 'define complex: all(p1, not(any(p2, p3)), atleast(2, p4, p5))';
      const ast = await parse(source);

      const extractText = (loc) => source.substring(loc.start.offset, loc.end.offset);

      const agg = ast.definitions[0];
      
      // Outer all() expression
      const allExpr = agg.expression;
      assert.equal(allExpr.type, 'all');
      assert.equal(extractText(allExpr.loc), 'all(p1, not(any(p2, p3)), atleast(2, p4, p5))');

      // First arg: simple reference
      assert.equal(allExpr.args[0].type, 'reference');
      assert.equal(extractText(allExpr.args[0].loc), 'p1');

      // Second arg: not() expression
      const notExpr = allExpr.args[1];
      assert.equal(notExpr.type, 'not');
      assert.equal(extractText(notExpr.loc), 'not(any(p2, p3))');

      // Inside not(): any() expression
      const anyExpr = notExpr.expr;
      assert.equal(anyExpr.type, 'any');
      assert.equal(extractText(anyExpr.loc), 'any(p2, p3)');

      // Inside any(): references
      assert.equal(extractText(anyExpr.args[0].loc), 'p2');
      assert.equal(extractText(anyExpr.args[1].loc), 'p3');

      // Third arg: atleast() expression
      const atleastExpr = allExpr.args[2];
      assert.equal(atleastExpr.type, 'atleast');
      assert.equal(atleastExpr.count, 2);
      assert.equal(extractText(atleastExpr.loc), 'atleast(2, p4, p5)');

      // Inside atleast(): references
      assert.equal(extractText(atleastExpr.args[0].loc), 'p4');
      assert.equal(extractText(atleastExpr.args[1].loc), 'p5');
    });

    it('should track locations with properties blocks', async () => {
      const source = `predicate is_adult: "Is patient 18+" 
  metadata: {
    desc: "Check DOB",
    version: 1
  }`;

      const ast = await parse(source);
      const extractText = (loc) => source.substring(loc.start.offset, loc.end.offset);

      const pred = ast.definitions[0];
      
      // The entire predicate including property block
      const fullText = extractText(pred.loc);
      assert.ok(fullText.includes('predicate is_adult'));
      assert.ok(fullText.includes('desc: "Check DOB"'));
      assert.ok(fullText.includes('version: 1'));
      assert.ok(fullText.includes('}'));

      // Verify it spans multiple lines
      assert.equal(pred.loc.start.line, 0);
      assert.ok(pred.loc.end.line > 0, 'should end on a later line');
      
      // Verify properties were parsed
      assert.ok(pred.properties);
      assert.equal(pred.properties.desc, 'Check DOB');
      assert.equal(pred.properties.version, 1);
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty source file', async () => {
      const source = '';
      const ast = await parse(source);

      assert.equal(ast.type, 'source_file');
      assert.equal(ast.definitions.length, 0);
    });

    it('should handle source with only comments', async () => {
      const source = `
        # Comment 1
        # Comment 2
      `;
      const ast = await parse(source);

      assert.equal(ast.definitions.length, 0);
    });

    it('should handle strings with escape sequences', async () => {
      const source = 'predicate p: "Line 1\\nLine 2\\tTabbed"';
      const ast = await parse(source);

      assert.equal(ast.definitions[0].question, 'Line 1\nLine 2\tTabbed');
    });

    it('should handle identifiers with underscores', async () => {
      const source = 'predicate has_valid_id_card: "Has valid ID?"';
      const ast = await parse(source);

      assert.equal(ast.definitions[0].id, 'has_valid_id_card');
    });

    it('should parse complex nested aggregators', async () => {
      const source = `
        predicate p1: "P1"
        predicate p2: "P2"
        predicate p3: "P3"
        define complex: all(p1, not(any(p2, p3)))
      `;
      const ast = await parse(source);

      const agg = ast.definitions[3];
      assert.equal(agg.expression.type, 'all');
      assert.equal(agg.expression.args[1].type, 'not');
      assert.equal(agg.expression.args[1].expr.type, 'any');
      assert.equal(agg.expression.args[1].expr.args.length, 2);
    });

    it('should reject empty aggregators', async () => {
      await assert.rejects(
        parse('define invalid: all()'),
        ParseError
      );
    });

    it('should reject non-integer aggregator counts', async () => {
      await assert.rejects(
        parse('define invalid: atleast(1.5, predicate)'),
        SyntaxError
      );
    });

    it('should reject invalid aggregator counts', async () => {
      await assert.rejects(
        parse('define invalid: atleast(0, predicate)'),
        ParseError
      );
    });

    it('should reject extra arguments inside not expressions', async () => {
      const source = `
predicate p: "Question"
define invalid: not(p, p)
`;
      await assert.rejects(parse(source), SyntaxError);
    });

    it('should reject negative metadata numbers instead of discarding the sign', async () => {
      const source = `
predicate p: "Question"
  metadata: { number: -1 }
`;
      await assert.rejects(parse(source), SyntaxError);
    });

    it('should reject missing closing tokens', async () => {
      const source = `
predicate p: "Question"
define invalid: all(p
`;
      await assert.rejects(parse(source), SyntaxError);
    });

    it('should accept integral citation pages written as decimals', async () => {
      const source = `
citation policy: {
  source_ref: "policy.pdf"
  regions: [{ page: 1.0, box: [[0,0],[1,0],[1,1],[0,1]] }]
}
`;
      const ast = await parse(source);
      assert.equal(ast.definitions[0].regions[0].page, 1);
    });

    it('should reject fractional citation page numbers', async () => {
      const source = `
citation policy: {
  source_ref: "policy.pdf"
  regions: [{ page: 1.5, box: [[0,0],[1,0],[1,1],[0,1]] }]
}
`;
      await assert.rejects(parse(source), StructuralError);
    });

    it('should reject false as citation regions instead of omitting it', async () => {
      const source = `
citation policy: { source_ref: "policy.pdf", regions: false }
`;
      await assert.rejects(parse(source), StructuralError);
    });
  });

  describe('Common Properties (New Syntax)', () => {
    it('should parse predicate with label', async () => {
      const source = `
        predicate is_adult: "Is patient 18?"
          label: "Adult Status Check"
      `;
      const ast = await parse(source);

      const pred = ast.definitions[0];
      assert.equal(pred.type, 'predicate_definition');
      assert.equal(pred.label, 'Adult Status Check');
    });

    it('should parse predicate with all common properties', async () => {
      const source = `
        predicate is_adult: "Is patient 18 or older?"
          label: "Adult Status Check"
          doc: "Verifies minimum age requirement"
          cite: [age_req, federal_law]
          context: "Must be strictly over 18"
          metadata: { priority: 1 }
      `;
      const ast = await parse(source);

      const pred = ast.definitions[0];
      assert.equal(pred.label, 'Adult Status Check');
      assert.equal(pred.doc, 'Verifies minimum age requirement');
      assert.deepEqual(pred.citation_refs.map(r => r.id), ['age_req', 'federal_law']);
      assert.equal(pred.context, 'Must be strictly over 18');
      assert.deepEqual(pred.properties, { priority: 1 });
    });

    it('should parse outcome with common properties', async () => {
      const source = `
        outcome approved: "Request approved"
          label: "Approved Status"
          doc: "All requirements met"
          cite: approval_policy
      `;
      const ast = await parse(source);

      const outcome = ast.definitions[0];
      assert.equal(outcome.type, 'outcome_definition');
      assert.equal(outcome.description, 'Request approved');
      assert.equal(outcome.label, 'Approved Status');
      assert.equal(outcome.doc, 'All requirements met');
      assert.deepEqual(outcome.citation_refs.map(r => r.id), ['approval_policy']);
    });

    it('should parse aggregator with common properties', async () => {
      const source = `
        predicate p1: "P1"
        define check: all(p1)
          label: "Basic Check"
          doc: "Core validation"
          cite: policy_doc
      `;
      const ast = await parse(source);

      const agg = ast.definitions[1];
      assert.equal(agg.type, 'aggregator_definition');
      assert.equal(agg.label, 'Basic Check');
      assert.equal(agg.doc, 'Core validation');
      assert.deepEqual(agg.citation_refs.map(r => r.id), ['policy_doc']);
    });

    it('should parse path with common properties', async () => {
      const source = `
        predicate p1: "P1"
        outcome approved: "Approved"
        path standard: p1 => approved
          label: "Standard Path"
          doc: "Normal flow"
          cite: [flow_doc, regulations]
      `;
      const ast = await parse(source);

      const path = ast.definitions[2];
      assert.equal(path.type, 'path');
      assert.equal(path.label, 'Standard Path');
      assert.equal(path.doc, 'Normal flow');
      assert.deepEqual(path.citation_refs.map(r => r.id), ['flow_doc', 'regulations']);
      assert.equal(path.outcome_ref.id, 'approved');
    });

    it('should parse single citation syntax', async () => {
      const source = `
        predicate p1: "P1"
          cite: single_citation
      `;
      const ast = await parse(source);

      const pred = ast.definitions[0];
      assert.deepEqual(pred.citation_refs.map(r => r.id), ['single_citation']);
    });

    it('should parse multiple citations in array syntax', async () => {
      const source = `
        predicate p1: "P1"
          cite: [cite1, cite2, cite3]
      `;
      const ast = await parse(source);

      const pred = ast.definitions[0];
      assert.deepEqual(pred.citation_refs.map(r => r.id), ['cite1', 'cite2', 'cite3']);
    });

    it('should reject duplicate label properties', async () => {
      const source = `
        predicate p1: "P1"
          label: "First"
          label: "Second"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        /Duplicate 'label' property/
      );
    });

    it('should reject duplicate doc properties', async () => {
      const source = `
        predicate p1: "P1"
          doc: "First"
          doc: "Second"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        /Duplicate 'doc' property/
      );
    });

    it('should reject duplicate metadata properties', async () => {
      const source = `
        predicate p1: "P1"
          metadata: { a: 1 }
          metadata: { b: 2 }
      `;
      
      await assert.rejects(
        async () => await parse(source),
        /Duplicate 'metadata' property/
      );
    });

    it('should reject duplicate cite properties', async () => {
      const source = `
        predicate p1: "P1"
          cite: cite1
          cite: cite2
      `;
      
      await assert.rejects(
        async () => await parse(source),
        /Duplicate 'cite' property/
      );
    });

    it('should reject context property on aggregators (grammar enforced)', async () => {
      const source = `
        predicate p1: "P1"
        define agg: all(p1)
          context: "This is not allowed"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          return true;
        }
      );
    });

    it('should reject context property on paths (grammar enforced)', async () => {
      const source = `
        predicate p1: "P1"
        outcome approved: "Approved"
        path test: p1 => approved
          context: "This is not allowed"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          return true;
        }
      );
    });

    it('should reject context property on outcomes (grammar enforced)', async () => {
      const source = `
        outcome approved: "Approved"
          context: "This is not allowed"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          assert.ok(error.message.includes('in outcome definition'));
          return true;
        }
      );
    });

    it('should allow context property on predicates', async () => {
      const source = `
        predicate is_adult: "Is patient 18+"
          context: "Check birth date"
      `;
      
      const ast = await parse(source);
      assert.equal(ast.definitions[0].context, 'Check birth date');
    });

    it('should reject unknown property on predicate', async () => {
      const source = `
        predicate p1: "P1"
          unknown_prop: "This property does not exist"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          return true;
        }
      );
    });

    it('should reject unknown property on outcome', async () => {
      const source = `
        outcome o1: "O1"
          foo: "bar"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          return true;
        }
      );
    });

    it('should reject unknown property on aggregator', async () => {
      const source = `
        predicate p1: "P1"
        define agg: all(p1)
          random: "invalid"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          return true;
        }
      );
    });

    it('should reject unknown property on path', async () => {
      const source = `
        predicate p1: "P1"
        outcome o1: "O1"
        path test: p1 => o1
          custom: "not allowed"
      `;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          return true;
        }
      );
    });
  });

  describe('Error Handling', () => {
    it('should throw SyntaxError for syntax error in path', async () => {
      const source = `predicate p1: "P1"
outcome o1: "O1"
path p: p1 @invalid => o1`;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          assert.ok(error.message.includes('in path'));
          assert.ok(error.loc);
          return true;
        }
      );
    });

    it('should throw SyntaxError for syntax error in property block', async () => {
      const source = `predicate p1: "P1"
  metadata: { valid: "value", @invalid }`;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          assert.ok(error.message.includes('in property block'));
          assert.ok(error.loc);
          return true;
        }
      );
    });

    it('should throw SyntaxError for syntax error in property array', async () => {
      const source = `predicate p1: "P1"
  metadata: { tags: ["valid", @invalid] }`;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          assert.ok(error.message.includes('in property array'));
          assert.ok(error.loc);
          return true;
        }
      );
    });

    it('should throw SyntaxError for syntax error in property object', async () => {
      const source = `predicate p1: "P1"
  metadata: { nested: { valid: "value", @invalid } }`;
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error.message.includes('Syntax error'));
          assert.ok(error.message.includes('in property object'));
          assert.ok(error.loc);
          return true;
        }
      );
    });
  });

  describe('Structural Error Handling', () => {
    it('should throw StructuralError with location for invalid string literal', async () => {
      // Malformed string that gets past grammar but fails parsing
      const source = 'predicate p1: "unclosed string';
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          // This might be caught as a syntax error by tree-sitter
          assert.ok(error instanceof ParseError);
          assert.ok(error.loc);
          assert.equal(typeof error.loc.start.line, 'number');
          assert.equal(typeof error.loc.start.column, 'number');
          return true;
        }
      );
    });

    it('should have location info for all errors', async () => {
      // Test that all errors include location info
      const testCases = [
        'predicate p1: "test" @invalid',     // Syntax error
        'outcome o1: "test" @invalid',       // Syntax error
        'define d1: all(p1 @invalid)',       // Syntax error in expression
      ];

      for (const source of testCases) {
        await assert.rejects(
          async () => await parse(source),
          (error) => {
            assert.ok(error instanceof ParseError, `Expected ParseError for: ${source}`);
            assert.ok(error.loc, `Expected location for: ${source}`);
            assert.ok(error.loc.start, `Expected start location for: ${source}`);
            assert.ok(error.loc.end, `Expected end location for: ${source}`);
            assert.equal(typeof error.loc.start.line, 'number');
            assert.equal(typeof error.loc.start.column, 'number');
            assert.equal(typeof error.loc.start.offset, 'number');
            return true;
          },
          `Failed to throw ParseError for: ${source}`
        );
      }
    });
  });

  describe('Error Type Hierarchy', () => {
    it('should throw SyntaxError for tree-sitter ERROR nodes', async () => {
      const source = 'predicate p1: "Valid" @unexpected';
      
      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(error instanceof SyntaxError);
          assert.ok(error instanceof ParseError);  // Hierarchy check
          assert.equal(error.name, 'SyntaxError');
          return true;
        }
      );
    });

    it('should verify all error types extend ParseError', () => {
      // Meta-test: verify error hierarchy is set up correctly
      const syntaxErr = new SyntaxError('test', { start: { line: 0, column: 0, offset: 0 }, end: { line: 0, column: 0, offset: 0 } });
      const structuralErr = new StructuralError('test', { start: { line: 0, column: 0, offset: 0 }, end: { line: 0, column: 0, offset: 0 } });
      const internalErr = new InternalParserError('test');

      assert.ok(syntaxErr instanceof ParseError);
      assert.ok(syntaxErr instanceof Error);
      assert.equal(syntaxErr.name, 'SyntaxError');

      assert.ok(structuralErr instanceof ParseError);
      assert.ok(structuralErr instanceof Error);
      assert.equal(structuralErr.name, 'StructuralError');

      assert.ok(internalErr instanceof Error);
      assert.equal(internalErr.name, 'InternalParserError');
      assert.ok(internalErr.message.includes('Internal parser error'));
    });

    it('should throw ParseError when tree-sitter returns ERROR as the root node', async () => {
      const source = '{"type":"foo_note_v1","items":[{"a":"b","c":"d"}]}';

      await assert.rejects(
        async () => await parse(source),
        (error) => {
          assert.ok(
            error instanceof ParseError,
            `Expected ParseError, got ${error.name}: ${error.message}`
          );
          assert.ok(
            !(error instanceof InternalParserError),
            'Root-ERROR input must not surface as InternalParserError'
          );
          assert.ok(error.loc, 'ParseError must carry location info');
          assert.equal(typeof error.loc.start.line, 'number');
          assert.equal(typeof error.loc.start.column, 'number');
          assert.equal(typeof error.loc.start.offset, 'number');
          return true;
        }
      );
    });
  });
});

describe('Conditional path arrows', () => {
  it('records the outgoing condition of each step including the final arrow', async () => {
    const ast = await parse('path fallback: requested => home !=> facility !=> review');
    const path = ast.definitions[0];
    assert.deepEqual(path.steps.map(step => step.id), ['requested', 'home', 'facility']);
    assert.deepEqual(path.conditions, [true, false, false]);
    assert.equal(path.outcome_ref.id, 'review');
    assert.equal(path.outcome_ref.loc.start.offset, 50);
  });
  it('retains the legacy AST shape for positive-only paths', async () => {
    const ast = await parse('path yes: check => approved');
    assert.equal(ast.definitions[0].conditions, undefined);
  });
  for (const arrow of ['! =>', '!>', '!=', '!!=>']) {
    it(`rejects malformed arrow ${arrow}`, async () => {
      await assert.rejects(parse(`path bad: p ${arrow} o`), ParseError);
    });
  }
});

describe('Duplicate properties', () => {
  for (const property of ['label: "x"', 'doc: "x"', 'cite: c', 'metadata: {}', 'context: "x"']) {
    const key = property.split(':')[0];
    it(`reports a repeated ${key} at its key`, async () => {
      const line = `  ${property}`;
      const error = await parse(`predicate a: "A"\n${line}\n${line}`).catch(e => e);
      assert.ok(error instanceof StructuralError, String(error));
      assert.deepEqual(
        [error.loc.start.line, error.loc.start.column, error.loc.end.line, error.loc.end.column],
        [2, 2, 2, 2 + key.length]
      );
    });
  }
});

describe('Carriage return line endings', () => {
  it('ends a comment at a carriage return', async () => {
    const ast = await parse('predicate a: "A?"\r# note\rpath p: a => y\routcome y: "Y"\r');
    assert.deepStrictEqual(ast.definitions.map((d) => d.type), ['predicate_definition', 'path', 'outcome_definition']);
  });
});
