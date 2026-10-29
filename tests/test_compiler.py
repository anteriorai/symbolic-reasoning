"""Tests for the pure Python SRG compiler."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from itertools import product
from pathlib import Path

import pytest

import symbolic_reasoning as sr
from symbolic_reasoning import (
    Answer,
    Coverage,
    SRGExecution,
    outcomes,
    reasoning_trace,
)
from symbolic_reasoning.compiler import (
    CompilerError,
    ParseError,
    compile_srg_ast,
    compile_srg_file,
    compile_srg_string,
    parse_srg,
)
from symbolic_reasoning.compiler.parser import SRGSyntaxError, StructuralError
from symbolic_reasoning.gen.py.ast import (
    AggregatorDefinition,
    CitationDefinition,
    OutcomeDefinition,
    PolicyContextDefinition,
    PredicateDefinition,
    SourceFile,
)
from symbolic_reasoning.models.srg_execution import _ready_predicates_with_contexts

from .scenarios import ANNOTATED_POLICY, INVALID_ASTS, first_step, last_path


def test_compiles_nested_expressions_and_metadata() -> None:
    source = """
policy_context: "Underwriting"
citation policy: {
  source_ref: "policy.pdf"
  filename: "policy.pdf"
  regions: [{ page: 1, box: [[0, 0], [1, 0], [1, 1], [0, 1]] }]
}
predicate is_adult: "Is the applicant an adult?"
  context: "Verify date of birth"
  cite: policy
  metadata: { priority: 1 }
predicate has_income: "Does the applicant have income?"
outcome approved: "Approved"
define eligible: all(is_adult, any(has_income, not(is_adult)))
  label: "Eligibility"
  cite: policy
path approval: root => eligible => approved
"""

    srg = compile_srg_string(source)

    assert srg.policy_context == "Underwriting"
    assert srg.predicates["is_adult"].context == "Verify date of birth"
    assert srg.predicates["is_adult"].metadata == {"priority": 1}
    assert srg.citations is not None
    assert srg.citations["policy"].regions is not None
    assert srg.citations["policy"].regions[0].page == 1
    assert any(aggregator.name == "eligible" for aggregator in srg.aggregators.values())


@pytest.mark.parametrize("context", [None, "", "Underwriting é🙂"])
def test_policy_context_through_all_entrypoints(
    tmp_path: Path, context: str | None
) -> None:
    source = """
predicate p: "Café 🙂"
  context: "Local context"
outcome o: "Outcome"
path decision: p => o
"""
    if context is not None:
        source += f'\npolicy_context: "{context}"'
    ast = parse_srg(source)
    declarations = [
        definition.root
        for definition in ast.definitions
        if isinstance(definition.root, PolicyContextDefinition)
    ]
    assert [declaration.value for declaration in declarations] == (
        [] if context is None else [context]
    )
    path = tmp_path / "policy.srg"
    path.write_text(source, encoding="utf-8")
    expected = compile_srg_string(source).model_dump()
    for srg in (
        compile_srg_ast(ast),
        compile_srg_string(source),
        compile_srg_file(path),
    ):
        assert srg.policy_context == context
        assert srg.predicates["p"].context == "Local context"
        assert srg.model_dump() == expected


def test_multiline_policy_context() -> None:
    source = '''policy_context: """
Use the 2026 policy.
Apply it to the application date.
"""'''
    assert compile_srg_string(source).policy_context == (
        "Use the 2026 policy.\nApply it to the application date."
    )


def test_duplicate_empty_policy_context() -> None:
    source = 'policy_context: ""\npolicy_context: "second"'
    ast = parse_srg(source)
    assert len(ast.definitions) == 2
    with pytest.raises(CompilerError, match="Duplicate policy_context") as error:
        compile_srg_ast(ast)
    assert error.value.loc is not None
    assert error.value.loc.start.line == 1


def test_policy_context_in_directly_constructed_ast() -> None:
    context = {
        "type": "policy_context_definition",
        "value": "",
        "loc": {
            "start": {"line": 0, "column": 0, "offset": 0},
            "end": {"line": 0, "column": 18, "offset": 18},
        },
    }
    ast = SourceFile.model_validate({"type": "source_file", "definitions": [context]})
    assert compile_srg_ast(ast).policy_context == ""
    duplicated = SourceFile.model_validate(
        {
            "type": "source_file",
            "definitions": [context, {**context, "value": "second"}],
        }
    )
    with pytest.raises(CompilerError, match="Duplicate policy_context"):
        compile_srg_ast(duplicated)


@pytest.mark.parametrize(
    "expression",
    ["all()", "any()", "none()", "atleast(1.5, predicate)", "atmost(0.5, predicate)"],
)
def test_rejects_empty_aggregators_and_non_integer_counts(expression: str) -> None:
    source = f"""\
predicate predicate: "Question"
outcome outcome: "Outcome"
path result: {expression} => outcome
"""

    with pytest.raises(ParseError):
        parse_srg(source)


def test_rejects_an_invalid_count_for_atleast() -> None:
    source = """
predicate predicate: "Question"
outcome outcome: "Outcome"
path result: atleast(0, predicate) => outcome
"""

    with pytest.raises(ParseError, match="at least 1"):
        parse_srg(source)


OPERATOR_KEYWORDS = ["all", "any", "none", "not", "atleast", "atmost", "exactly"]


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
def test_rejects_operator_keywords_as_references(keyword: str, template: str) -> None:
    source = template.format(k=keyword)

    with pytest.raises(ParseError, match=f"'{keyword}' is a reserved keyword") as error:
        parse_srg(source)
    assert error.value.loc is not None
    line = source.splitlines()[error.value.loc.start.line]
    start = error.value.loc.start.column
    assert line[start : start + len(keyword)] == keyword
    assert line.rfind(keyword) == start


@pytest.mark.parametrize("keyword", OPERATOR_KEYWORDS)
def test_accepts_operator_keywords_as_unreferenced_names(keyword: str) -> None:
    source = f"""\
citation {keyword}: {{ source_ref: "s" }}
predicate {keyword}: "Never referenced"
predicate a: "A"
  cite: {keyword}
outcome y: "Y"
path {keyword}: a => y
"""

    srg = compile_srg_string(source)
    assert keyword in srg.predicates


@pytest.mark.parametrize(
    ("last_line", "typo"),
    [
        ("path p: a => bb => y", "bb"),
        ("path p: all(a, bb) => y", "bb"),
        ("path p: a => nope", "nope"),
    ],
)
def test_undefined_reference_errors_point_at_the_typo(
    last_line: str, typo: str
) -> None:
    source = f'predicate a: "A"\noutcome y: "Y"\n{last_line}'

    with pytest.raises(CompilerError, match=f"'{typo}' not found") as error:
        compile_srg_string(source)
    loc = error.value.loc
    assert loc is not None
    assert (loc.start.line, loc.start.column) == (2, last_line.index(typo))
    assert (loc.end.line, loc.end.column) == (2, last_line.index(typo) + len(typo))


@pytest.mark.parametrize(
    ("second", "message"),
    [
        ('predicate a: "Again?"', "'a' is already defined as a predicate"),
        ('outcome a: "Again"', "'a' is already defined as a predicate"),
        ("define a: all(b)", "'a' is already defined as a predicate"),
        ('predicate y: "Again?"', "'y' is already defined as an outcome"),
        ("define d: all(b)", "'d' is already defined as a define"),
        ('citation c: { source_ref: "s2" }', "'c' is already defined as a citation"),
    ],
)
def test_rejects_a_second_definition_of_a_name(second: str, message: str) -> None:
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
    assert str(error.value) == message
    assert error.value.loc is not None
    assert error.value.loc.start.line == 6


@pytest.mark.parametrize("name", ["root", "Root"])
@pytest.mark.parametrize(
    "definition", ['predicate {n}: "Q?"', 'outcome {n}: "O"', "define {n}: all(b)"]
)
def test_rejects_definitions_named_like_the_graph_root(
    name: str, definition: str
) -> None:
    source = f'predicate b: "B?"\noutcome y: "Y"\npath p: b => y\n{definition.format(n=name)}'

    with pytest.raises(CompilerError, match="is reserved") as error:
        compile_srg_string(source)
    assert error.value.loc is not None
    assert error.value.loc.start.line == 3


@pytest.mark.parametrize("name", ["A1", "SN_2", "SN3", "Root"])
@pytest.mark.parametrize(
    "definition", ['predicate {n}: "Q?"', 'outcome {n}: "O"', "define {n}: all(b)"]
)
def test_rejects_definitions_named_like_graph_ids(name: str, definition: str) -> None:
    source = f'predicate b: "B?"\noutcome y: "Y"\npath p: b => y\n{definition.format(n=name)}'

    with pytest.raises(CompilerError) as error:
        compile_srg_string(source)
    assert str(error.value) == f"'{name}' is reserved for graph ids"
    assert error.value.loc is not None
    assert error.value.loc.start.line == 3


def test_names_that_only_resemble_generated_ids_compile() -> None:
    srg = compile_srg_string("""\
citation a: { source_ref: "s" }
predicate a: "A?"
  cite: a
predicate A1x: "B?"
predicate SN_: "C?"
outcome a1: "Y"
path p: all(a, A1x, SN_) => a1
""")

    assert set(srg.predicates) == {"a", "A1x", "SN_"}
    assert list(srg.aggregators) == ["A1"]


ROOT_PLACEMENTS = {
    "a => root => y": "can only start a path",
    "all(root, a) => y": "can only start a path",
    "not(root) => y": "can only start a path",
    "d => y": "can only start a path",
    "root !=> a => y": "never takes a false edge",
}


@pytest.mark.parametrize(("steps", "message"), ROOT_PLACEMENTS.items())
def test_rejects_root_outside_the_start_of_a_path(steps: str, message: str) -> None:
    source = (
        f'predicate a: "A?"\noutcome y: "Y"\ndefine d: all(root, a)\npath p: {steps}'
    )

    with pytest.raises(CompilerError, match=message) as error:
        compile_srg_string(source)
    loc = error.value.loc
    assert loc is not None
    line = source.splitlines()[loc.start.line]
    assert line[loc.start.column : loc.end.column] == "root"


@pytest.mark.parametrize(
    "steps", ["root => a => y", "root => y", "a => y", "root => a !=> y"]
)
def test_accepts_root_at_the_start_of_a_path(steps: str) -> None:
    srg = compile_srg_string(f'predicate a: "A?"\noutcome y: "Y"\npath p: {steps}')

    assert all(
        edge.source == "Root" or edge.target != "Root" for edge in srg.edges.values()
    )


@pytest.mark.parametrize("coverage", [Coverage.MINIMAL, Coverage.REACHABLE])
@pytest.mark.parametrize(("a", "b", "c"), list(product([False, True], repeat=3)))
def test_shared_predicates_preserve_outcomes_and_reuse_answers(
    a: bool, b: bool, c: bool, coverage: Coverage
) -> None:
    source = """
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
outcome y: "Y"
path one: a => b => x
path two: c => b => y
"""
    srg = compile_srg_string(source)
    values = {"a": a, "b": b, "c": c}
    calls: Counter[str] = Counter()

    execution = SRGExecution(srg=srg)
    # Exercise the compiled graph through the execution frontier, independent of
    # any oracle API.
    while ready := _ready_predicates_with_contexts(execution, coverage):
        calls.update(ready.keys())
        execution = SRGExecution(
            srg=srg,
            answers={
                **execution.answers,
                **{
                    predicate_id: Answer(is_met=values[predicate_id], reasoning="Test")
                    for predicate_id in ready
                },
            },
        )
    expected = (["x"] if a and b else []) + (["y"] if c and b else [])
    assert sorted(o.id for o in outcomes(execution)) == expected
    assert all(count == 1 for count in calls.values())
    for path in reasoning_trace(execution).outcome_paths:
        expected_steps = ["a", "b"] if path.outcome_id == "x" else ["c", "b"]
        assert [step.predicate_id for step in path.steps] == expected_steps


def test_repeated_steps_and_reverse_order_do_not_create_cycles() -> None:
    source = """
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path one: a => a => b => x
path two: b => a => y
"""
    srg = compile_srg_string(source)
    # Each intermediate occurrence has its own continuation.
    assert sum(n.item_id == "a" for n in srg.nodes.values()) == 3
    assert sum(n.item_id == "b" for n in srg.nodes.values()) == 2
    pending = ["Root"]
    visited: set[str] = set()
    while pending:
        node = pending.pop()
        assert node not in visited
        visited.add(node)
        pending.extend(e.target for e in srg.edges.values() if e.source == node)
    assert len(visited) == len(srg.nodes)


def test_root_and_terminal_outcome_nodes_remain_shared() -> None:
    source = """
predicate a: "A"
predicate b: "B"
predicate c: "C"
outcome x: "X"
path one: root => a => b => x
path two: root => c => b => x
"""
    srg = compile_srg_string(source)
    assert sum(n.item_id == "Root" for n in srg.nodes.values()) == 1
    assert sum(n.item_id == "x" for n in srg.nodes.values()) == 1
    assert sum(n.item_id == "b" for n in srg.nodes.values()) == 2


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("all(a, b)", [False, False, False, True]),
        ("any(a, b)", [False, True, True, True]),
        ("none(a, b)", [True, False, False, False]),
        ("not(a)", [True, True, False, False]),
        ("atleast(2, a, b)", [False, False, False, True]),
        ("atleast(3, a, b)", [False, False, False, False]),
        ("atmost(1, a, b)", [True, True, True, False]),
        ("atmost(0, a, b)", [True, False, False, False]),
        ("exactly(1, a, b)", [False, True, True, False]),
        ("exactly(0, a, b)", [True, False, False, False]),
        ("all(a, not(b))", [False, False, True, False]),
    ],
)
def test_compiled_operator_truth_tables(expression: str, expected: list[bool]) -> None:
    source = f"""
predicate a: "A"
predicate b: "B"
outcome o: "O"
path decision: {expression} => o
"""
    srg = compile_srg_string(source)
    for (a, b), result in zip(product([False, True], repeat=2), expected, strict=True):
        execution = SRGExecution(
            srg=srg,
            answers={
                "a": Answer(is_met=a, reasoning="Test"),
                "b": Answer(is_met=b, reasoning="Test"),
            },
        )
        assert ("o" in {o.id for o in outcomes(execution)}) is result


@pytest.mark.parametrize(("steps", "corrupt", "message", "located_at"), INVALID_ASTS)
def test_invalid_ast_is_rejected_at_the_offending_node(
    steps: str,
    corrupt: Callable[[SourceFile], None],
    message: str,
    located_at: str,
) -> None:
    ast = parse_srg(f'predicate a: "A"\noutcome o: "O"\npath p: {steps}')
    expected = last_path(ast).loc if located_at == "path" else first_step(ast).root.loc
    corrupt(ast)

    with pytest.raises(CompilerError, match=message) as error:
        compile_srg_ast(ast)

    assert error.value.loc == expected


@pytest.mark.parametrize(
    ("source", "message", "reference"),
    [
        (
            'citation c: { source_ref: "s" }\npredicate p: "Q"\n  cite: d',
            "Citation 'd' is not defined",
            "d",
        ),
        ('outcome o: "O"\n  cite: d', "Citation 'd' is not defined", "d"),
        (
            'predicate p: "Q"\ndefine unused: all(p)\n  cite: d',
            "Citation 'd' is not defined",
            "d",
        ),
        (
            'citation c: { source_ref: "s" }\npredicate p: "Q"\n  cite: [c, c]',
            "Citation 'c' is cited twice",
            "c]",
        ),
        (
            'predicate p: "Q"\noutcome o: "O"\n  cite: p',
            "'p' is a predicate; cite: takes citation ids",
            "p",
        ),
    ],
)
def test_cite_must_name_each_declared_citation_once(
    source: str, message: str, reference: str
) -> None:
    with pytest.raises(CompilerError, match=message) as error:
        compile_srg_string(source)

    line = source.count("\n")
    assert error.value.loc is not None
    assert (error.value.loc.start.line, error.value.loc.start.column) == (
        line,
        source.splitlines()[line].rindex(reference),
    )


def test_cite_may_name_a_citation_declared_later() -> None:
    srg = compile_srg_string(
        'predicate p: "Q"\n  cite: [c, d]\ncitation c: { source_ref: "s" }\n'
        'citation d: { source_ref: "t" }'
    )

    assert srg.predicates["p"].citation_ids == ["c", "d"]


CR_POLICY = (
    'predicate adult: "Is the applicant an adult?"\routcome approved: "Approved"\r'
    'outcome denied: "Denied"\r# minors are denied\rpath deny: adult !=> denied\r'
    "path approve: adult => approved\r"
)


def test_a_comment_ends_at_a_carriage_return() -> None:
    srg = compile_srg_string(CR_POLICY)

    assert len(srg.edges) == 3
    assert srg.outcomes.keys() == {"approved", "denied"}


def test_a_carriage_return_policy_compiles_the_same_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "policy.srg"
    path.write_bytes(CR_POLICY.encode())

    assert compile_srg_file(path) == compile_srg_string(CR_POLICY)


DEFINE_CYCLES = {
    "define d: all(a, d)": "d -> d",
    "define d: all(a, e)\ndefine e: not(d)": "d -> e -> d",
    "define d: any(a, all(a, e))\ndefine e: f\ndefine f: all(d)": "d -> e -> f -> d",
}


@pytest.mark.parametrize(("defines", "cycle"), DEFINE_CYCLES.items())
def test_rejects_defines_that_refer_to_themselves(defines: str, cycle: str) -> None:
    source = f'predicate a: "A?"\noutcome y: "Y"\n{defines}\npath p: d => y'

    with pytest.raises(CompilerError, match=f"refers to itself: {cycle}") as error:
        compile_srg_string(source)
    loc = error.value.loc
    assert loc is not None
    line = source.splitlines()[loc.start.line]
    assert line[loc.start.column : loc.end.column] == "d"


def test_a_define_shared_by_two_branches_is_not_a_cycle() -> None:
    srg = compile_srg_string("""\
predicate a: "A?"
predicate b: "B?"
outcome y: "Y"
define shared: all(a)
define either: any(shared, b)
path p: all(shared, either) => y
""")

    assert len(srg.aggregators) == 3


def test_every_annotation_reaches_the_graph() -> None:
    ast = parse_srg(ANNOTATED_POLICY)
    srg = compile_srg_ast(ast)
    symbols = {
        **srg.predicates,
        **srg.outcomes,
        **{a.name: a for a in srg.aggregators.values() if a.name},
    }
    for definition in (wrapped.root for wrapped in ast.definitions):
        if isinstance(definition, CitationDefinition):
            assert srg.citations is not None
            assert srg.citations[definition.id].metadata == definition.metadata
        elif isinstance(
            definition, PredicateDefinition | OutcomeDefinition | AggregatorDefinition
        ):
            symbol = symbols[definition.id]
            refs = definition.citation_refs
            assert (
                symbol.label,
                symbol.doc,
                symbol.citation_ids,
                symbol.metadata,
            ) == (
                definition.label,
                definition.doc,
                [ref.id for ref in refs] if refs else None,
                definition.properties,
            )
    assert srg.predicates["adult"].question == "Is the applicant an adult?"


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ('predicate a "A?"', SRGSyntaxError),
        ('predicate a: "A?"\n  label: "x"\n  label: "y"', StructuralError),
        ('outcome o: "O"\npath p: missing => o', sr.CompilerError),
    ],
)
def test_compile_errors_are_importable_from_the_package(
    source: str, error: type[sr.ParseError] | type[sr.CompilerError]
) -> None:
    with pytest.raises(error) as caught:
        sr.compile_srg_string(source)
    assert caught.value.loc is not None
