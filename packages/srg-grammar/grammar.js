/**
 * Tree-sitter grammar for SRG v2
 * 
 * Defines the syntax for Symbolic Reasoning Graph language:
 * - predicates: predicate id: "question"
 * - outcomes: outcome id: "description"
 * - named aggregators: define id: expression
 * - citations: citation id { ... }
 * - named paths: path id: expr => outcome
 * 
 * All components support common properties:
 * - label: "human readable label"
 * - doc: "human readable documentation"
 * - cite: citation_id or [citation_id1, citation_id2]
 * - context: "additional context"
 * - metadata: { ... }
 */

module.exports = grammar({
  name: 'srg',

  extras: $ => [
    /\s/,           // whitespace
    $.comment       // comments
  ],

  rules: {
    source_file: $ => repeat($._definition),

    _definition: $ => choice(
      $.policy_context_definition,
      $.predicate_definition,
      $.outcome_definition,
      $.aggregator_definition,
      $.citation_definition,
      $.path
    ),

    // A lone carriage return ends a line too.
    comment: $ => token(seq('#', /[^\r\n]*/)),

    policy_context_definition: $ => seq(
      'policy_context',
      ':',
      field('value', $.string)
    ),

    predicate_definition: $ => seq(
      'predicate',
      field('id', $.identifier),
      ':',
      field('question', $.string),
      repeat($._predicate_property)
    ),

    outcome_definition: $ => seq(
      'outcome',
      field('id', $.identifier),
      ':',
      field('description', $.string),
      repeat($._common_property)
    ),

    aggregator_definition: $ => seq(
      'define',
      field('id', $.identifier),
      ':',
      field('expression', $.expression),
      repeat($._common_property)
    ),

    citation_definition: $ => seq(
      'citation',
      field('id', $.identifier),
      ':',
      $.property_block
    ),

    // Common properties that can be attached to any component (except predicates which have additional properties)
    _common_property: $ => choice(
      $.label_property,
      $.doc_property,
      $.cite_property,
      $.metadata_property
    ),

    // Predicate-specific properties (all common properties + context)
    _predicate_property: $ => choice(
      $._common_property,
      $.context_property
    ),

    label_property: $ => seq(
      'label',
      ':',
      field('value', $.string)
    ),

    doc_property: $ => seq(
      'doc',
      ':',
      field('value', $.string)
    ),

    cite_property: $ => seq(
      'cite',
      ':',
      choice(
        field('citation', $.identifier),
        $.citation_array
      )
    ),

    citation_array: $ => seq(
      '[',
      field('citation', $.identifier),
      repeat(seq(',', field('citation', $.identifier))),
      optional(','),
      ']'
    ),

    context_property: $ => seq(
      'context',
      ':',
      field('value', $.string)
    ),

    metadata_property: $ => seq(
      'metadata',
      ':',
      $.property_block
    ),

    property_block: $ => seq(
      '{',
      optional(seq(
        $.property,
        repeat(seq(optional(','), $.property)),
        optional(',')
      )),
      '}'
    ),

    property: $ => seq(
      field('key', $.identifier),
      ':',
      field('value', $.property_value)
    ),

    property_value: $ => choice(
      $.string,
      $.number,
      $.boolean,
      $.property_array,
      $.property_object
    ),

    property_array: $ => seq(
      '[',
      optional(seq(
        $.property_value,
        repeat(seq(',', $.property_value)),
        optional(',')
      )),
      ']'
    ),

    property_object: $ => seq(
      '{',
      optional(seq(
        $.property,
        repeat(seq(optional(','), $.property)),
        optional(',')
      )),
      '}'
    ),

    boolean: $ => choice('true', 'false'),

    // Supports chaining: expr => expr => ... => outcome
    // Examples: 
    //   path standard: root => all(p1, p2) => outcome1
    //   path simple: all(p1, p2) => any(p3, p4) => outcome1
    path: $ => seq(
      'path',
      field('id', $.identifier),
      ':',
      field('step', $.expression),
      repeat(seq(choice('=>', '!=>'), field('step', $.expression))),
      choice('=>', '!=>'),
      field('outcome', $.identifier),
      repeat($._common_property)
    ),

    expression: $ => choice(
      $.reference,
      $.all_expression,
      $.any_expression,
      $.none_expression,
      $.atleast_expression,
      $.atmost_expression,
      $.exactly_expression,
      $.not_expression
    ),

    // Reference to predicate or named aggregator
    reference: $ => $.identifier,

    all_expression: $ => seq(
      'all',
      '(',
      $.argument_list,
      ')'
    ),

    any_expression: $ => seq(
      'any',
      '(',
      $.argument_list,
      ')'
    ),

    none_expression: $ => seq(
      'none',
      '(',
      $.argument_list,
      ')'
    ),

    atleast_expression: $ => seq(
      'atleast',
      '(',
      field('count', $.integer),
      ',',
      $.argument_list,
      ')'
    ),

    atmost_expression: $ => seq(
      'atmost',
      '(',
      field('count', $.integer),
      ',',
      $.argument_list,
      ')'
    ),

    exactly_expression: $ => seq(
      'exactly',
      '(',
      field('count', $.integer),
      ',',
      $.argument_list,
      ')'
    ),

    not_expression: $ => seq(
      'not',
      '(',
      field('expr', $.expression),
      ')'
    ),

    argument_list: $ => seq(
      $.expression,
      repeat(seq(',', $.expression))
    ),

    identifier: $ => /[A-Za-z_][A-Za-z0-9_]*/,

    number: $ => choice(
      /\d+\.\d+/,  // float (must come first for precedence)
      /\d+/        // integer
    ),

    integer: $ => /\d+/,

    // Supports both regular and triple-quoted strings
    string: $ => choice(
      seq(
        '"',
        repeat(choice(
          token.immediate(prec(1, /[^"\\]+/)),
          $.escape_sequence
        )),
        '"'
      ),
      seq(
        '"""',
        repeat(choice(
          token.immediate(prec(1, /[^"\\]+/)),
          $.escape_sequence,
          '"'
        )),
        '"""'
      )
    ),

    escape_sequence: $ => token.immediate(seq(
      '\\',
      choice(
        /[\\'"nrt]/,
        /u[0-9a-fA-F]{4}/,
        /U[0-9a-fA-F]{8}/
      )
    ))
  }
});
