"""Differential integration tests for the Python and TypeScript compilers.

Compare compiled JSON and acceptance/rejection. Locations use the same UTF-16
units, but error recovery spans and wording need not match between parsers.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from symbolic_reasoning.compiler import (
    CompilerError,
    ParseError,
    compile_srg_ast,
    compile_srg_string,
    parse_srg,
)
from symbolic_reasoning.gen.py.ast import SourceFile

from .scenarios import ANNOTATED_POLICY, INVALID_ASTS

ROOT = Path(__file__).parents[1]
TS_RUNNER = ROOT / "tests" / "compiler_parity" / "compile_ts.mjs"


def _typescript(
    source: str,
    *,
    locations: bool = False,
    ast: bool = False,
    compile_ast: dict[str, object] | None = None,
    message: bool = False,
) -> dict[str, Any]:
    completed = subprocess.run(
        ["node", str(TS_RUNNER)],
        input=json.dumps(
            {
                "source": source,
                "locations": locations,
                "ast": ast,
                "compile_ast": compile_ast,
                "message": message,
            }
        ),
        capture_output=True,
        check=True,
        cwd=ROOT,
        text=True,
        timeout=10,
    )
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


def _assert_compilation_parity(source: str) -> None:
    srg = compile_srg_string(source)
    python = srg.model_dump(mode="json", exclude_none=True)
    # The TS wire format always includes this nullable top-level field.
    python["policy_context"] = srg.policy_context
    assert _typescript(source) == {"ok": True, "value": python}


@pytest.fixture(autouse=True)
def _require_parity_environment() -> None:
    if os.environ.get("SRG_PARITY") != "1":
        pytest.skip("set SRG_PARITY=1 after building the TypeScript compiler")
    if not (ROOT / "packages" / "srg-compiler" / "dist" / "index.js").exists():
        pytest.fail("TypeScript compiler has not been built")


def test_complete_policy() -> None:
    source = """
# Forward references, nested expressions, and common properties.
path approval: root => eligible => approved
  label: "Approval path"
  doc: "Path documentation"
  cite: [policy, other,]
  metadata: { owner: "team" }
path fallback: none(is_adult) => review
define eligible: all(is_adult, any(has_income, has_guarantor))
  label: "Eligibility"
  doc: "Eligibility documentation"
  cite: policy
  metadata: { tier: "standard" }
predicate is_adult: "Is the applicant an adult?"
  label: "Adult"
  doc: "Verify date of birth"
  context: "Use the supplied government ID"
  cite: policy
  metadata: { priority: 1, tags: ["core", true,], nested: { enabled: false } }
predicate has_income: "Does the applicant have income?"
predicate has_guarantor: "Does the applicant have a guarantor?"
outcome approved: "Approved"
  label: "Approval"
  doc: "Approval documentation"
  cite: [policy, other]
  metadata: { notify: true }
outcome review: "Needs review"
citation policy: {
  source_ref: "sha256:abc123"
  filename: "policy.pdf"
  excerpt: "Eligibility policy"
  regions: [{ page: 4, box: [[0, 0], [10, 0], [10, 10], [0, 10]] }]
  revision: 2
}
citation other: { source_ref: "other.pdf" }
"""
    _assert_compilation_parity(source)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize(
    "declaration",
    [
        'predicate p: "Question"',
        'outcome o: "Outcome"',
        "define a: all(p)",
        "path decision: p => o",
    ],
)
def test_comments_between_properties(
    declaration: str, standalone: bool, newline: str
) -> None:
    separator = (
        f"{newline}# é🙂 comment{newline}" if standalone else f" # é🙂 comment{newline}"
    )
    source = (
        'predicate p: "Question"' if not declaration.startswith("predicate") else ""
    ) + newline
    source += (
        'outcome o: "Outcome"' if not declaration.startswith("outcome") else ""
    ) + newline
    source += (
        f'{declaration}{separator}  label: "Label"{separator}  doc: "Documentation"'
    )
    ast = parse_srg(source).model_dump(mode="json", exclude_none=True)
    assert ast["definitions"][-1]["label"] == "Label"
    assert ast["definitions"][-1]["doc"] == "Documentation"
    assert _typescript(source, ast=True) == {
        "ok": True,
        "value": ast,
    }
    _assert_compilation_parity(source)


@pytest.mark.parametrize(
    "optional_fields",
    [False, True],
)
def test_ast_optional_fields_match_typescript(optional_fields: bool) -> None:
    predicate_properties = (
        'context: "" label: "" doc: "" metadata: {}' if optional_fields else ""
    )
    citation_properties = (
        'filename: "" excerpt: "" regions: []' if optional_fields else ""
    )
    source = f"""
citation c: {{source_ref: "doc" {citation_properties}}}
predicate p: "Q" {predicate_properties}
outcome o: "O"
define a: all(p)
path decision: a => o
"""
    assert _typescript(source, ast=True) == {
        "ok": True,
        "value": parse_srg(source).model_dump(mode="json", exclude_none=True),
    }
    _assert_compilation_parity(source)


@pytest.mark.parametrize(
    "expression",
    [
        "a",
        "root",
        "all(a, b)",
        "any(a, b)",
        "none(a, b)",
        "not(a)",
        "atleast(1, a, b)",
        "atleast(3, a, b)",
        "atmost(0, a, b)",
        "exactly(0, a, b)",
        "exactly(2, a, b)",
        "all(any(a, not(b)), exactly(1, a, b))",
    ],
)
def test_expressions(expression: str) -> None:
    source = f"""
predicate a: "A"
predicate b: "B"
outcome result: "Result"
path decision: {expression} => result
"""
    _assert_compilation_parity(source)


@pytest.mark.parametrize(
    "paths",
    [
        "path one: a => b => x\npath two: c => b => y",
        "path one: a => b => x\npath two: b => y",
        "path one: a => b => x\npath two: b => a => y",
        "path one: a => a => x",
        "path one: root => a => b => x\npath two: root => c => b => x",
        "path one: a => shared => x\npath two: c => shared => y",
        "path one: a => all(b) => x\npath two: c => all(b) => y",
        "define alias: b\npath one: a => alias => x\npath two: c => alias => y",
    ],
)
def test_reused_path_steps(paths: str) -> None:
    source = f"""
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
outcome y: "Y"
define shared: all(b)
{paths}
"""
    _assert_compilation_parity(source)


@pytest.mark.parametrize("policy_context", [None, "", "Policy context é🙂"])
def test_policy_context(policy_context: str | None) -> None:
    source = 'predicate p: "Q" outcome o: "O" path decision: p => o'
    if policy_context is not None:
        source += f"\npolicy_context: {json.dumps(policy_context, ensure_ascii=False)}"
    _assert_compilation_parity(source)
    assert compile_srg_string(source).policy_context == policy_context


def test_multiline_policy_context() -> None:
    source = '''
policy_context: """
  Use the 2026 policy.
  Preserve é🙂 and \\n as written.
"""
predicate p: "Question"
  context: "Local context"
outcome o: "Outcome"
path decision: p => o
'''
    _assert_compilation_parity(source)


@pytest.mark.parametrize(
    "source",
    [
        'policy_context: "first" policy_context: "second"',
        'policy_context: "" predicate p: "Q" policy_context: "second"',
        "policy_context: 42",
        'policy_context "missing colon"',
        "policy_context:",
    ],
)
def test_invalid_policy_context(source: str) -> None:
    with pytest.raises((ParseError, CompilerError)):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


def test_duplicate_policy_context_diagnostic() -> None:
    source = 'policy_context: ""\npolicy_context: "second"'
    with pytest.raises(CompilerError) as error:
        compile_srg_string(source)
    assert error.value.loc is not None
    assert _typescript(source) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
    }


@pytest.mark.parametrize(
    ("steps", "corrupt"),
    [(steps, corrupt) for steps, corrupt, _, _ in INVALID_ASTS],
)
def test_invalid_ast_diagnostic(
    steps: str, corrupt: Callable[[SourceFile], None]
) -> None:
    ast = parse_srg(f'predicate a: "A"\noutcome o: "O"\npath p: {steps}')
    corrupt(ast)
    with pytest.raises(CompilerError) as error:
        compile_srg_ast(ast)
    assert error.value.loc is not None
    assert _typescript(
        "", compile_ast=ast.model_dump(mode="json", exclude_none=True, warnings=False)
    ) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
    }


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda ast: ast["definitions"][3].update(type="path_definition"),
        lambda ast: ast["definitions"][4].update(
            condition=ast["definitions"][4].pop("conditions")
        ),
        lambda ast: ast["definitions"][4]["steps"][0].update(negated=True),
    ],
    ids=["unknown definition type", "misspelled conditions", "unknown expression key"],
)
def test_misshapen_ast_is_rejected_by_both(corrupt: Any) -> None:
    source = (
        'predicate sanctioned: "On a sanctions list?"\noutcome approved: "Approved"\n'
        'outcome denied: "Denied"\npath block: sanctioned => denied\n'
        "path ok: sanctioned !=> approved"
    )
    ast = parse_srg(source).model_dump(mode="json", exclude_none=True)
    corrupt(ast)
    with pytest.raises(ValueError):
        compile_srg_ast(SourceFile.model_validate(ast))
    assert _typescript("", compile_ast=ast)["ok"] is False


@pytest.mark.parametrize(
    "source",
    [
        'citation c: { source_ref: "s" }\npredicate p: "Q"\n  cite: d',
        'outcome o: "O"\n  cite: d',
        'predicate p: "Q"\ndefine unused: all(p)\n  cite: d',
        'citation c: { source_ref: "s" }\npredicate p: "Q"\n  cite: [c, c]',
    ],
)
def test_cite_diagnostic(source: str) -> None:
    with pytest.raises(CompilerError) as error:
        compile_srg_string(source)
    assert error.value.loc is not None
    assert _typescript(source) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
    }


def test_annotations_match_typescript() -> None:
    _assert_compilation_parity(ANNOTATED_POLICY)


def test_empty_citation_metadata_matches_typescript() -> None:
    ast = parse_srg('citation c: { source_ref: "s" }').model_dump(
        mode="json", exclude_none=True
    )
    ast["definitions"][0]["metadata"] = {}
    srg = compile_srg_ast(SourceFile.model_validate(ast))
    python = srg.model_dump(mode="json", exclude_none=True)
    python["policy_context"] = srg.policy_context
    assert python["citations"]["c"]["metadata"] == {}
    assert _typescript("", compile_ast=ast) == {"ok": True, "value": python}


def test_metadata_never_replaces_fields() -> None:
    metadata = {"question": "inner", "context": "inner", "label": "inner", "custom": {}}
    source = """
predicate p: "Q"
  context: "outer"
  label: "outer"
  metadata: { question: "inner", context: "inner", label: "inner", custom: {} }
"""
    _assert_compilation_parity(source)
    predicate = compile_srg_string(source).predicates["p"]
    assert (predicate.question, predicate.context, predicate.label) == (
        "Q",
        "outer",
        "outer",
    )
    assert predicate.metadata == metadata


@pytest.mark.parametrize(
    "defines",
    [
        "define d: all(a, d)",
        "define d: all(a, e)\ndefine e: not(d)",
        "define d: any(a, all(a, e))\ndefine e: f\ndefine f: all(d)",
    ],
)
def test_define_cycles(defines: str) -> None:
    source = f'predicate a: "A?"\noutcome y: "Y"\n{defines}\npath p: d => y'
    with pytest.raises(CompilerError) as error:
        compile_srg_string(source)
    assert error.value.loc is not None
    assert _typescript(source) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
    }


@pytest.mark.parametrize("page", ["0", "1", "1.0", "01.00"])
def test_integral_citation_pages(page: str) -> None:
    source = f"""
citation c: {{
  source_ref: "doc"
  regions: [{{ page: {page}, box: [[0, 0], [1.5, 0], [1.5, 1], [0, 1]] }}]
}}
"""
    _assert_compilation_parity(source)


def test_empty_optional_values() -> None:
    source = """
citation c: { source_ref: "doc", filename: "", excerpt: "", regions: [] }
predicate p: "" label: "" doc: "" context: "" metadata: {}
outcome o: "" label: "" doc: "" metadata: {}
path decision: p => o
"""
    _assert_compilation_parity(source)
    citations = compile_srg_string(source).model_dump(mode="json")["citations"]
    assert citations["c"]["regions"] == []


@pytest.mark.parametrize("source", ["", "# Only a comment\n", 'predicate unused: "Q"'])
def test_empty_and_unused_definitions(source: str) -> None:
    _assert_compilation_parity(source)


def test_strings_and_unicode_locations() -> None:
    source = r'''
predicate p: "Café 🙂\n\"quoted\" \\slash\t\u00e9"
  doc: """  Multiline é🙂
documentation with # and => left intact.  """
outcome o: "结果" path decision: p => o
'''
    _assert_compilation_parity(source)
    locations = [
        d.root.loc.model_dump() for d in parse_srg(source).definitions if d.root.loc
    ]
    assert _typescript(source, locations=True) == {"ok": True, "value": locations}


@pytest.mark.parametrize(
    "source",
    [
        r'predicate p: """a\"""b"""',
        r'predicate p: """raw \n \u00e9 \U0001f642"""',
        '\ufeffpredicate p: "Q"',
        'predicate p: """\ufeff\u00a0Q\u00a0\ufeff"""',
        'predicate p: """\u0085Q\u0085"""',
    ],
)
def test_raw_strings_and_bom(source: str) -> None:
    _assert_compilation_parity(source)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_location_units(newline: str) -> None:
    source = (
        f'policy_context: "Policy é🙂"{newline}'
        f'predicate p: "é🙂" outcome o: "O"{newline}path decision: p => o'
    )
    locations = [
        d.root.loc.model_dump() for d in parse_srg(source).definitions if d.root.loc
    ]
    assert _typescript(source, locations=True) == {"ok": True, "value": locations}
    outcome_loc = parse_srg(source).definitions[2].root.loc
    assert outcome_loc is not None
    assert outcome_loc.start.column == 19


@pytest.mark.parametrize(
    "expression",
    [
        "all()",
        "any()",
        "none()",
        "atleast(1)",
        "atmost(0)",
        "exactly(0)",
        "atleast(1.5, p)",
        "atmost(0.5, p)",
        "exactly(1.5, p)",
        "atleast(0, p)",
        "all(p,)",
        "not(p, p)",
        "atleast(1٢, p)",
    ],
)
def test_invalid_expressions(expression: str) -> None:
    source = f'predicate p: "Q" outcome o: "O" path decision: {expression} => o'
    with pytest.raises(ParseError):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


@pytest.mark.parametrize(
    "source",
    [
        'predicate p: "Q" label: "one" label: "two"',
        'predicate p: "Q" context: "one" context: "two"',
        'outcome o: "O" context: "invalid"',
        'predicate p: "Q" unknown: "invalid"',
        'predicate p: "Q" metadata: {number: 1٢}',
        'predicate p: "Q" metadata: {number: 1.٢}',
        'predicate p: "Q" metadata: {number: -1}',
        'predicate p: "Q" metadata: {number: 1',
        'predicate p: "Q" metadata: {values: [1, 2}',
        r'predicate p: "a\bb"',
        r'predicate p: "a\/b"',
        r'predicate p: """a\qb"""',
        r'predicate p: "\u00zz"',
        '\u0085predicate p: "Q"',
        '\u00a0predicate p: "Q"',
        'predicate p: "unterminated',
        'citation c: { filename: "doc" }',
        'citation c: { source_ref: "doc", regions: "invalid" }',
        'citation c: { source_ref: "doc", regions: "" }',
        'citation c: { source_ref: "doc", regions: false }',
        'citation c: { source_ref: "doc", regions: 0 }',
        'citation c: { source_ref: "doc", regions: [1] }',
        'citation c: { source_ref: "doc", regions: [{page: 1, box: []}] }',
    ],
)
def test_invalid_source(source: str) -> None:
    with pytest.raises(ParseError):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


@pytest.mark.parametrize("page", ["1.5", "true", '"1"'])
def test_invalid_citation_pages(page: str) -> None:
    source = f"""
citation c: {{ source_ref: "doc",
  regions: [{{page: {page}, box: [[0,0],[1,0],[1,1],[0,1]]}}]
}}
"""
    with pytest.raises(ParseError):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


@pytest.mark.parametrize(
    "source",
    [
        'outcome o: "O" path decision: missing => o',
        'predicate p: "Q" path decision: p => missing',
    ],
)
def test_missing_symbols(source: str) -> None:
    with pytest.raises(CompilerError):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


def test_medical_necessity_shared_prefix_and_negative_edge_parity() -> None:
    source = (ROOT / "tests" / "fixtures" / "medical-necessity-branches.srg").read_text()
    _assert_compilation_parity(source)
    assert _typescript(source, ast=True) == {
        "ok": True,
        "value": parse_srg(source).model_dump(mode="json", exclude_none=True),
    }


@pytest.mark.parametrize(
    "paths",
    [
        "path one: a => b => x\npath two: a !=> b => y",
        "path one: a => x\npath two: a !=> x",
        "path one: all(a, b) => x\npath two: root => all(a, b) !=> y",
        "path one: a => a !=> b => x\npath two: b !=> a => y",
    ],
)
def test_conditional_path_parity(paths: str) -> None:
    source = (
        'predicate a: "A"\npredicate b: "B"\noutcome x: "X"\noutcome y: "Y"\n' + paths
    )
    _assert_compilation_parity(source)
    assert _typescript(source, ast=True) == {
        "ok": True,
        "value": parse_srg(source).model_dump(mode="json", exclude_none=True),
    }


@pytest.mark.parametrize("arrow", ["! =>", "!>", "!=", "!!=>"])
def test_malformed_arrow_rejection_parity(arrow: str) -> None:
    source = f'predicate p: "P"\noutcome o: "O"\npath bad: p {arrow} o'
    with pytest.raises(ParseError):
        parse_srg(source)
    assert _typescript(source)["ok"] is False


OPERATOR_KEYWORDS = ["all", "any", "none", "not", "atleast", "atmost", "exactly"]
CONTEXTUAL_KEYWORDS = [
    "predicate",
    "outcome",
    "define",
    "citation",
    "path",
    "label",
    "doc",
    "cite",
    "context",
    "metadata",
    "true",
    "false",
]


@pytest.mark.parametrize("keyword", OPERATOR_KEYWORDS)
@pytest.mark.parametrize(
    "template",
    [
        'predicate {k}: "Q"\noutcome y: "Y"\npath p: {k} => y',
        'predicate a: "A"\noutcome {k}: "Y"\npath p: a => {k}',
        'predicate a: "A"\noutcome y: "Y"\ndefine {k}: all(a)\npath p: {k} => y',
        'predicate {k}: "Q"\npredicate a: "A"\noutcome y: "Y"\npath p: all(a, {k}) => y',
    ],
)
def test_operator_keywords_as_references(keyword: str, template: str) -> None:
    source = template.format(k=keyword)
    with pytest.raises(ParseError):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


@pytest.mark.parametrize("keyword", OPERATOR_KEYWORDS)
def test_operator_keywords_as_unreferenced_names(keyword: str) -> None:
    _assert_compilation_parity(f"""
citation {keyword}: {{ source_ref: "s" }}
predicate {keyword}: "Never referenced"
predicate a: "A"
  cite: {keyword}
outcome y: "Y"
path {keyword}: a => y
""")


@pytest.mark.parametrize("keyword", CONTEXTUAL_KEYWORDS)
def test_contextual_keywords_as_references(keyword: str) -> None:
    _assert_compilation_parity(f"""
predicate {keyword}: "Q"
outcome y: "Y"
define d_{keyword}: all({keyword})
path p: d_{keyword} => y
""")


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ('predicate a: "A"\noutcome y: "Y"\npath p: a => bb => y', "CompilerError"),
        ('predicate a: "A"\noutcome y: "Y"\npath p: all(a, bb) => y', "CompilerError"),
        (
            'predicate a: "A"\noutcome y: "Y"\ndefine d: any(bb)\npath p: d => y',
            "CompilerError",
        ),
        ('predicate a: "A"\noutcome y: "Y"\npath p: a => nope', "CompilerError"),
        ('predicate a: "A"\n  label: "x"\n  label: "y"', "StructuralError"),
        ('predicate a: "A"\n  doc: "x"\n  doc: "y"', "StructuralError"),
        ('predicate a: "A"\n  cite: c\n  cite: c', "StructuralError"),
        ('predicate a: "A"\n  metadata: {}\n  metadata: {}', "StructuralError"),
        ('predicate a: "A"\n  context: "x"\n  context: "y"', "StructuralError"),
    ],
)
def test_diagnostic_locations(source: str, name: str) -> None:
    try:
        compile_srg_string(source)
    except (ParseError, CompilerError) as error:
        assert type(error).__name__ == name
        assert error.loc is not None
        assert _typescript(source) == {
            "ok": False,
            "name": name,
            "line": error.loc.start.line,
            "column": error.loc.start.column,
        }
    else:
        pytest.fail("Python compiled the source")


def test_comment_ends_at_a_carriage_return_parity() -> None:
    source = (
        'predicate adult: "Is the applicant an adult?"\routcome approved: "Approved"\r'
        'outcome denied: "Denied"\r# minors are denied\rpath deny: adult !=> denied\r'
        "path approve: adult => approved\r"
    )
    _assert_compilation_parity(source)


@pytest.mark.parametrize(
    "second",
    [
        'predicate a: "Again?"',
        'outcome a: "Again"',
        "define a: all(b)",
        'predicate y: "Again?"',
        "define d: all(b)",
        'citation c: { source_ref: "s2" }',
        'predicate root: "Q?"',
        'outcome Root: "O"',
        "define root: all(b)",
        'predicate A1: "Q?"',
        'outcome SN_2: "O"',
        "define SN3: all(b)",
    ],
)
def test_duplicate_and_reserved_names(second: str) -> None:
    source = f"""\
citation c: {{ source_ref: "s" }}
predicate a: "A?"
predicate b: "B?"
outcome y: "Y"
define d: all(a, b)
path p: d => y
{second}"""
    with pytest.raises(CompilerError) as error:
        compile_srg_string(source)
    assert error.value.loc is not None
    assert _typescript(source) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
    }


@pytest.mark.parametrize("path", ["toString => y", "a => constructor"])
def test_inherited_object_names_are_not_definitions(path: str) -> None:
    source = f'predicate a: "A?"\noutcome y: "Y"\npath p: {path}'
    with pytest.raises(CompilerError):
        compile_srg_string(source)
    assert _typescript(source)["ok"] is False


@pytest.mark.parametrize(
    "steps",
    [
        "a => root => y",
        "all(root, a) => y",
        "not(root) => y",
        "d => y",
        "root !=> a => y",
    ],
)
def test_root_placement(steps: str) -> None:
    source = (
        f'predicate a: "A?"\noutcome y: "Y"\ndefine d: all(root, a)\npath p: {steps}'
    )
    with pytest.raises(CompilerError) as error:
        compile_srg_string(source)
    assert error.value.loc is not None
    assert _typescript(source) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
    }


# Names Object.prototype already has once passed srg-compile's lookups (#97).
VALUE_OF_POLICY = """\
predicate sanctioned: "Is the applicant on a sanctions list?"
outcome valueOf: "Escalate valuation"
outcome approved: "Approved"
define valueOf: not(sanctioned)
path approve: valueOf => approved
"""


def test_object_prototype_names_are_rejected_with_the_same_message() -> None:
    message = "'valueOf' is already defined as an outcome"
    with pytest.raises(CompilerError) as error:
        compile_srg_string(VALUE_OF_POLICY)
    assert str(error.value) == message
    assert error.value.loc is not None
    assert _typescript(VALUE_OF_POLICY, message=True) == {
        "ok": False,
        "name": "CompilerError",
        "line": error.value.loc.start.line,
        "column": error.value.loc.start.column,
        "message": message,
    }
