from collections.abc import Callable

from symbolic_reasoning import SRGBuilder
from symbolic_reasoning.gen.py.ast import Expression, Path, SourceFile
from symbolic_reasoning.models import (
    AllStrategy,
    AtLeastStrategy,
    AtMostStrategy,
    ExactlyStrategy,
)
from symbolic_reasoning.models.srg import SRG

from .utils import SolverScenario, SolverStep

# ============================================================================
# SRG factory functions
# ============================================================================


def make_complex_srg() -> SRG:
    """Complex SRG with nested aggregators exercising all strategy types.

    Graph structure:
      Root → a6_node (True) → a7_node (True) → O1_node (True)
      Root → a10_node (True) → O2_node (True)

    Strategies present: AllStrategy (a1,a5,a7,a10), AtLeast (a2,a6,a9),
    AtMost (a3), Exactly (a4,a8).
    """
    srg = SRGBuilder()
    srg.policy_context = "Complex test policy"

    p1 = srg.add_predicate("P1")
    p2 = srg.add_predicate("P2")
    p3 = srg.add_predicate("P3")
    p4 = srg.add_predicate("P4")
    p5 = srg.add_predicate("P5")
    p6 = srg.add_predicate("P6")
    p7 = srg.add_predicate("P7")
    p8 = srg.add_predicate("P8")
    p9 = srg.add_predicate("P9")
    p10 = srg.add_predicate("P10")
    p11 = srg.add_predicate("P11")
    p12 = srg.add_predicate("P12")
    p13 = srg.add_predicate("P13")
    p14 = srg.add_predicate("P14")
    p15 = srg.add_predicate("P15")
    p16 = srg.add_predicate("P16")

    o1 = srg.add_outcome("O1")
    o2 = srg.add_outcome("O2")

    a1 = srg.add_aggregator(AllStrategy(), True, [p1, p2])
    a2 = srg.add_aggregator(AtLeastStrategy(count=1), True, [p3, p4])
    a4 = srg.add_aggregator(ExactlyStrategy(count=0), True, [p5, p6])
    a5 = srg.add_aggregator(AllStrategy(), True, [p4, p7, p8])
    a3 = srg.add_aggregator(AtMostStrategy(count=2), True, [a1, a2, p16])
    a6 = srg.add_aggregator(AtLeastStrategy(count=2), True, [a3, a4, a5])
    a7 = srg.add_aggregator(AllStrategy(), True, [p9, p10])
    a8 = srg.add_aggregator(ExactlyStrategy(count=2), True, [p12, p13, p14])
    a9 = srg.add_aggregator(AtLeastStrategy(count=1), True, [a8, p11])
    a10 = srg.add_aggregator(AllStrategy(), True, [a9, p15])

    a6_node = srg.add_node(a6)
    a7_node = srg.add_node(a7)
    a10_node = srg.add_node(a10)
    o1_node = srg.add_node(o1)
    o2_node = srg.add_node(o2)

    srg.add_edge("Root", a6_node, condition=True)
    srg.add_edge(a6_node, a7_node, condition=True)
    srg.add_edge("Root", a10_node, condition=True)
    srg.add_edge(a7_node, o1_node, condition=True)
    srg.add_edge(a10_node, o2_node, condition=True)

    return srg.build()


# ============================================================================
# Scenario constants
# ============================================================================

COMPLEX_SRG_O1 = SolverScenario(
    steps=[
        SolverStep(["P1", "P12"], [False, True]),
        SolverStep(["P5", "P13"], [False, True]),
        SolverStep(["P6", "P14"], [False, True]),
        SolverStep(["P11", "P9"], [True, True]),
        SolverStep(["P15", "P10"], [False, True]),
    ],
    expected_outcome_paths=[
        ("O1", ["P1", "P5", "P6", "P9", "P10"]),
    ],
    # a10 branch dead-end: P15=False → a10=False → no True edge to O2.
    # Reports the whole a10 subtree in argument order: a8's, then P11, then P15.
    expected_distinct_paths=[
        ["P12", "P13", "P14", "P11", "P15"],
        ["P1", "P5", "P6", "P9", "P10"],
    ],
)

COMPLEX_SRG_O2 = SolverScenario(
    steps=[
        SolverStep(["P1", "P12"], [False, True]),
        SolverStep(["P5", "P13"], [True, True]),
        SolverStep(["P4", "P14"], [True, False]),
        SolverStep(["P7", "P15"], [True, True]),
        SolverStep(["P8"], [True]),
        SolverStep(["P9"], [False]),
    ],
    expected_outcome_paths=[
        # P14 is answered under a8's Exactly(2) but is not one of the two counted.
        ("O2", ["P12", "P13", "P14", "P15"]),
    ],
    # a6 terminates at a7 (P9=False). P5 is included though a4 evaluated False;
    # P4 appears under both a3→a2 and a5 but is reported once.
    expected_distinct_paths=[
        ["P12", "P13", "P14", "P15"],
        ["P1", "P4", "P5", "P7", "P8", "P9"],
    ],
)

COMPLEX_SRG_BOTH_OUTCOMES = SolverScenario(
    steps=[
        SolverStep(["P1", "P12"], [False, True]),
        SolverStep(["P5", "P13"], [False, True]),
        SolverStep(["P6", "P14"], [False, False]),
        SolverStep(["P15", "P9"], [True, True]),
        SolverStep(["P10"], [True]),
    ],
    expected_outcome_paths=[
        ("O1", ["P1", "P5", "P6", "P9", "P10"]),
        ("O2", ["P12", "P13", "P14", "P15"]),
    ],
    # a6: a3+a4 meets atleast(2) → a5 never asked, so no P4/P7/P8 to report.
    expected_distinct_paths=[
        ["P12", "P13", "P14", "P15"],
        ["P1", "P5", "P6", "P9", "P10"],
    ],
)


# ============================================================================
# ASTs a tool could hand to a compiler, broken in one place each
# ============================================================================
def last_path(ast: SourceFile) -> Path:
    path = ast.definitions[-1].root
    assert isinstance(path, Path)
    return path


def first_step(ast: SourceFile) -> Expression:
    """The first step expression of the last path."""
    return last_path(ast).steps[0]


INVALID_ASTS: list[tuple[str, Callable[[SourceFile], None], str, str]] = [
    (
        "a => o",
        lambda ast: last_path(ast).steps.clear(),
        "Path 'p' has no steps",
        "path",
    ),
    (
        "all(a) => o",
        lambda ast: setattr(first_step(ast).root, "args", []),
        "Aggregators require at least one argument",
        "step",
    ),
    (
        "not(a) => o",
        lambda ast: setattr(first_step(ast).root, "expr", None),
        "'not' needs an expression",
        "step",
    ),
    (
        "atleast(1, a) => o",
        lambda ast: setattr(first_step(ast).root, "count", 0),
        "'atleast' needs a whole-number count from 1 to 9007199254740991",
        "step",
    ),
    (
        "atleast(1, a) => o",
        lambda ast: setattr(first_step(ast).root, "count", 1.5),
        "'atleast' needs a whole-number count from 1 to 9007199254740991",
        "step",
    ),
    (
        "atleast(1, a) => o",
        lambda ast: setattr(first_step(ast).root, "count", 10**21),
        "'atleast' needs a whole-number count from 1 to 9007199254740991",
        "step",
    ),
    (
        "exactly(1, a) => o",
        lambda ast: setattr(first_step(ast).root, "count", 1e19),
        "'exactly' needs a whole-number count from 0 to 9007199254740991",
        "step",
    ),
    (
        "atmost(1, a) => o",
        lambda ast: setattr(first_step(ast).root, "count", -1),
        "'atmost' needs a whole-number count from 0 to 9007199254740991",
        "step",
    ),
    (
        "exactly(1, a) => o",
        lambda ast: setattr(first_step(ast).root, "count", 1.5),
        "'exactly' needs a whole-number count from 0 to 9007199254740991",
        "step",
    ),
]


ANNOTATED_POLICY = """
citation guide: { source_ref: "guide.pdf", page_note: "p. 4" }
predicate adult: "Is the applicant an adult?"
  label: "Adult"
  doc: "Age on the application date"
  cite: guide
  metadata: { priority: 1, question: "Not the question" }
predicate income: "Does the applicant have income?"
  metadata: {}
define of_age: adult
  label: "Of age"
  cite: guide
  metadata: { section: "2.1" }
define eligible: all(of_age, income)
  doc: "Section 2"
  metadata: { owner: "underwriting" }
outcome approved: "Approved"
  label: "Approval"
  metadata: { template: "B" }
path approve: eligible => approved
"""
