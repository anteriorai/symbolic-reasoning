"""Conditional path edges and prefix sharing preserve decisions and graph structure."""

from itertools import product
from pathlib import Path

import pytest

from symbolic_reasoning import (
    Answer,
    Coverage,
    SRGBuilder,
    SRGExecution,
    apply_answers,
    compile_srg_file,
    compile_srg_string,
    is_resolved,
    outcomes,
)
from symbolic_reasoning.compiler import (
    CompilerError,
    ParseError,
    compile_srg_ast,
    parse_srg,
)
from symbolic_reasoning.gen.py.ast import Path as PathDefinition
from symbolic_reasoning.models.srg_execution import _ready_predicates_with_contexts

from .utils import asked

SUPPORT = """
predicate requested: "Requested?"
predicate home: "Home ready?"
predicate facility: "Facility ready?"
outcome approved: "Approved"
outcome review: "Needs review"
path home_ok: requested => home => approved
path facility_ok: requested => home !=> facility => approved
path failed: requested => home !=> facility !=> review
"""


@pytest.mark.parametrize("coverage", list(Coverage))
@pytest.mark.parametrize(
    ("requested", "home", "facility"), list(product([False, True], repeat=3))
)
def test_fallback_decisions_and_evidence(
    requested: bool, home: bool, facility: bool, coverage: Coverage
) -> None:
    graph = compile_srg_string(SUPPORT)
    assert len(graph.nodes) == 6
    execution = SRGExecution(srg=graph)
    values = {"requested": requested, "home": home, "facility": facility}
    batches = []
    while pending := _ready_predicates_with_contexts(execution, coverage):
        batches.append(list(pending))
        if "facility" in pending:
            assert pending["facility"] == ("requested", "home")
            assert execution.answers["home"].is_met is False
        execution = apply_answers(
            execution,
            {key: Answer(is_met=values[key], reasoning="Evidence") for key in pending},
        )
    expected = [] if not requested else ["approved" if home or facility else "review"]
    assert [outcome.id for outcome in outcomes(execution)] == expected
    assert batches == [["requested"]] + ([["home"]] if requested else []) + (
        [["facility"]] if requested and not home else []
    )


def test_unknown_does_not_follow_a_negative_edge() -> None:
    graph = compile_srg_string('predicate p: "P"\noutcome o: "O"\npath no: p !=> o')
    execution = SRGExecution(srg=graph)
    assert not is_resolved(execution)
    assert asked(execution) == ["p"]
    assert not graph.aggregators


@pytest.mark.parametrize("include_positive", [False, True])
def test_add_edge_rejects_existing_compiled_negative_edge(
    include_positive: bool,
) -> None:
    source = 'predicate p: "P"\noutcome o: "O"\npath no: p !=> o'
    if include_positive:
        source += "\npath yes: p => o"
    graph = SRGBuilder.from_srg(compile_srg_string(source))
    edge = next(edge for edge in graph.edges.values() if not edge.condition)
    before = graph.model_dump()
    with pytest.raises(ValueError, match="duplicate edge"):
        graph.add_edge(edge.source, edge.target, condition=False)
    assert graph.model_dump() == before


def test_opposite_edges_to_same_outcome_are_retained() -> None:
    graph = compile_srg_string(
        'predicate p: "P"\noutcome o: "O"\npath yes: p => o\npath no: p !=> o'
    )
    node = next(n.id for n in graph.nodes.values() if n.item_id == "p")
    assert {edge.condition for edge in graph.edges.values() if edge.source == node} == {
        True,
        False,
    }
    for value in (False, True):
        assert (
            outcomes(
                SRGExecution(
                    srg=graph, answers={"p": Answer(is_met=value, reasoning="Test")}
                )
            )[0].id
            == "o"
        )


def test_divergence_by_condition_keeps_later_occurrences_separate() -> None:
    graph = compile_srg_string("""
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path yes: a => b => x
path no: a !=> b => y
""")
    assert sum(n.item_id == "a" for n in graph.nodes.values()) == 1
    assert sum(n.item_id == "b" for n in graph.nodes.values()) == 2
    for a, b in product([False, True], repeat=2):
        execution = SRGExecution(
            srg=graph,
            answers={
                k: Answer(is_met=v, reasoning="Test")
                for k, v in {"a": a, "b": b}.items()
            },
        )
        assert [o.id for o in outcomes(execution)] == (["x" if a else "y"] if b else [])


def test_shared_inline_prefix_ignores_locations_and_explicit_root() -> None:
    graph = compile_srg_string("""
predicate a: "A"
predicate b: "B"
outcome x: "X"
outcome y: "Y"
path one: root => all(a, b) => x
path two: all(a, b) !=> y
""")
    assert len(graph.aggregators) == 1
    assert len([e for e in graph.edges.values() if e.source == "Root"]) == 1


@pytest.mark.parametrize(
    ("path", "support_label"),
    [
        (Path(__file__).parent / "fixtures/msk-branches.srg", "Support need"),
        (
            Path(__file__).parents[1] / "examples/data/msk-review/policy.srg",
            "Support need · either",
        ),
    ],
)
def test_msk_topology_matches_the_manually_authored_graph(
    path: Path, support_label: str
) -> None:
    graph = compile_srg_file(path)
    assert len(graph.predicates) == 25
    assert len(graph.nodes) == 14
    assert len(graph.edges) == 22
    assert len(graph.aggregators) == 8
    assert len([e for e in graph.edges.values() if e.source == "Root"]) == 4
    named = {a.name: a for a in graph.aggregators.values()}
    support = named["support_need"]
    assert support.label == support_label
    assert support.id in named["home_criteria"].argument_ids
    assert support.id in named["facility_criteria"].argument_ids

    def symbol(node_id: str) -> str:
        item = graph.nodes[node_id].item_id
        return graph.aggregators[item].name if item in graph.aggregators else item

    actual = {
        (symbol(e.source), e.condition, symbol(e.target)) for e in graph.edges.values()
    }
    expected = set()
    for request, criterion in [
        ("fracture_requested", "fracture_criteria"),
        ("degeneration_requested", "degeneration_criteria"),
        ("rehabilitation_requested", "rehab_need"),
        ("support_requested", "home_criteria"),
    ]:
        expected.update({("Root", True, request), (request, True, criterion)})
    for criterion, yes, no in [
        ("fracture_criteria", "approved", "needs_review"),
        ("degeneration_criteria", "alternatives", "needs_review"),
        ("alternatives", "approved", "needs_review"),
        ("rehab_need", "rehab_plan", "needs_review"),
        ("rehab_plan", "approved", "needs_review"),
        ("home_criteria", "approved", "facility_criteria"),
        ("facility_criteria", "approved", "needs_review"),
    ]:
        expected.update({(criterion, True, yes), (criterion, False, no)})
    assert actual == expected


def test_conditions_match_steps_and_legacy_ast_defaults_to_positive() -> None:
    ast = parse_srg('predicate p: "P"\noutcome o: "O"\npath no: p !=> o')
    path = ast.definitions[-1].root
    assert isinstance(path, PathDefinition)
    assert path.conditions == [False]
    path.conditions = None
    assert all(e.condition for e in compile_srg_ast(ast).edges.values())
    path.conditions = [True, False]
    with pytest.raises(CompilerError, match="one boolean per step"):
        compile_srg_ast(ast)


@pytest.mark.parametrize("arrow", ["! =>", "!>", "!=", "!!=>"])
def test_malformed_negative_arrow_is_rejected(arrow: str) -> None:
    with pytest.raises(ParseError):
        parse_srg(f'predicate p: "P"\noutcome o: "O"\npath no: p {arrow} o')
