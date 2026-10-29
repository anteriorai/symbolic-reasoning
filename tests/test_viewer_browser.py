"""Check playback, inspection, and layout in Chromium."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from symbolic_reasoning import (
    Answer,
    ExecutionHistory,
    SRGBuilder,
    SRGExecution,
    load_history_file,
    record_execution,
)
from symbolic_reasoning.models import SRG, AllStrategy
from symbolic_reasoning.viewer import save_history_html

pytestmark = pytest.mark.skipif(
    os.environ.get("SRG_VIEWER_BROWSER") != "1",
    reason="Set SRG_VIEWER_BROWSER=1 to run Chromium checks",
)


@pytest.fixture
def browser() -> Iterator[Any]:
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        yield browser
        browser.close()


def test_offline_playback_inspector_and_trace(
    browser: Any, tmp_path: Path, underwriting_policy: SRG
) -> None:
    execution = SRGExecution(srg=underwriting_policy)

    attack = "</script><script>window.attacked = true</script>"
    with record_execution(ExecutionHistory.from_execution(execution)) as recorder:
        recorder.record({"has_good_credit": Answer(is_met=True, reasoning=attack)})
        recorder.record(
            {
                id_: Answer(
                    is_met=id_ != "has_down_payment", reasoning="Verified application"
                )
                for id_ in execution.srg.predicates
                if id_ != "has_good_credit"
            }
        )
    path = tmp_path / "replay.html"
    save_history_html(recorder.export_history(), path)
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.goto(path.as_uri())
    assert page.locator("#step-label").inner_text() == "Initial state"
    positions = page.locator(".card").evaluate_all(
        "cards => cards.map(c => [c.style.left, c.style.top, c.offsetHeight])"
    )
    page.locator("#next").click()
    assert page.locator("#step-label").inner_text() == "Batch 1 of 2"
    page.locator(".requirement.leaf").filter(has_text="Credit score").first.click()
    assert attack in page.locator("#inspector").inner_text()
    assert page.evaluate("window.attacked") is None
    page.locator("#timeline").fill("2")
    page.locator("#overview").click()
    assert page.locator("#run-status").inner_text() == "Decision resolved"
    trace = page.locator(".trace-link").filter(has_text="Sent to manual review")
    trace.focus()
    page.keyboard.press("Enter")
    assert trace.evaluate("node => node === document.activeElement")
    assert page.locator(".trace-step").count() > 0
    assert page.locator(".card.in-trace").count() > 0
    page.keyboard.press("Enter")
    assert trace.evaluate("node => node === document.activeElement")
    assert trace.get_attribute("aria-expanded") == "false"
    assert page.locator(".trace-step").count() == 0
    assert page.locator(".card.in-trace").count() == 0
    page.keyboard.press("Enter")
    page.locator("#inspector summary").click()
    explored = page.locator(".trace-link").filter(has_text="Explored path").first
    explored.focus()
    page.keyboard.press("Enter")
    assert explored.evaluate("node => node === document.activeElement")
    assert explored.get_attribute("aria-expanded") == "true"
    assert trace.get_attribute("aria-expanded") == "false"
    page.locator(".outcome .card-header").filter(
        has_text="Sent to manual review"
    ).click()
    page.locator("#inspector .trace-link").click()
    assert page.locator("#inspector h2").inner_text() == "Sent to manual review"
    assert page.locator(".trace-step").count() > 0
    assert positions == page.locator(".card").evaluate_all(
        "cards => cards.map(c => [c.style.left, c.style.top, c.offsetHeight])"
    )
    page.locator("#previous").click()
    assert page.locator(".trace-step").count() == 0
    page.locator("#play").click()
    page.wait_for_function(
        "document.getElementById('step-label').textContent === 'Batch 2 of 2'"
    )
    page.reload()
    assert page.locator("#step-label").inner_text() == "Initial state"
    assert page.locator("#cards .execution-card").count() == len(execution.srg.nodes)
    page.locator("#timeline").fill("2")
    assert page.locator("#run-status").inner_text() == "Decision resolved"
    assert all(url.startswith("file:") for url in requests)
    assert not errors
    page.close()


def test_small_screen_and_empty_run(browser: Any, tmp_path: Path) -> None:
    with record_execution(
        ExecutionHistory.from_execution(SRGExecution(srg=SRGBuilder().build()))
    ) as recorder:
        path = tmp_path / "empty.html"
        save_history_html(recorder.export_history(), path)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(path.as_uri())
    assert page.locator("#play").is_disabled()
    assert page.locator(".card").count() == 1
    assert page.locator("#run-status").inner_text() == "Decision resolved"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.locator("#zoom-in").click()
    page.locator("#fit").click()
    page.close()


@pytest.mark.parametrize("width,height", [(1200, 800), (390, 844)])
def test_large_batch_keeps_graph_and_controls_visible(
    browser: Any, tmp_path: Path, width: int, height: int
) -> None:
    srg = SRGBuilder()
    predicates = [
        srg.add_predicate(f"Question {i}: " + "description " * 9) for i in range(60)
    ]
    requirements = srg.add_aggregator(AllStrategy(), True, predicates)
    srg.add_edge("Root", srg.add_node(requirements))
    with record_execution(
        ExecutionHistory.from_execution(SRGExecution(srg=srg.build()))
    ) as recorder:
        recorder.record(
            {id_: Answer(is_met=True, reasoning="Yes") for id_ in predicates}
        )
        path = tmp_path / "batch.html"
        save_history_html(recorder.export_history(), path)
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(path.as_uri())
    page.locator("#next").click()
    assert page.locator("#batch-summary").inner_text() == "60 answers applied"
    assert page.locator("#viewport").evaluate("node => node.clientHeight") > 150
    assert page.locator("footer").evaluate(
        "node => node.getBoundingClientRect().bottom <= window.innerHeight"
    )
    assert page.locator("#inspector .answer-link").count() == 60
    page.close()


def test_shared_expressions_stay_compact_and_can_be_inspected(
    browser: Any, tmp_path: Path
) -> None:
    srg = SRGBuilder()
    a, b = srg.add_predicate("A"), srg.add_predicate("B")
    for index in range(14):
        a, b = (
            b,
            srg.add_aggregator(AllStrategy(), True, [a, b], name=f"Expression {index}"),
        )
    srg.add_edge("Root", srg.add_node(b))
    with record_execution(
        ExecutionHistory.from_execution(SRGExecution(srg=srg.build()))
    ) as recorder:
        path = tmp_path / "nested.html"
        save_history_html(recorder.export_history(), path)
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.goto(path.as_uri())
    # Expanding every occurrence would make shared-expression cards grow exponentially.
    assert page.locator(".requirement").count() <= 2 * len(srg.aggregators)
    assert page.locator(".requirement-group.shared").count() > 0
    page.locator(".requirement.nested").filter(has_text="Expression 12").first.click()
    for index in range(12, 0, -1):
        assert page.locator("#inspector h2").inner_text() == f"Expression {index}"
        page.locator("#inspector .answer-link").filter(
            has_text=f"Expression {index - 1}"
        ).click()
    page.locator("#inspector .answer-link").filter(has_text="UnansweredA").click()
    assert page.locator("#inspector h2").inner_text() == "A"
    page.close()


def test_corrections_and_backward_seeks_restore_answers_and_traces(
    browser: Any, tmp_path: Path
) -> None:
    srg = SRGBuilder()
    predicate = srg.add_predicate("Eligible?")
    node = srg.add_node(predicate)
    srg.add_edge("Root", node).add_edge(node, srg.add_node(srg.add_outcome("Approved")))
    with record_execution(
        ExecutionHistory.from_execution(
            SRGExecution(
                srg=srg.build(),
                answers={
                    predicate: Answer(
                        is_met=False,
                        reasoning="Initial reasoning",
                    ),
                },
            )
        )
    ) as recorder:
        recorder.record(
            {predicate: Answer(is_met=True, reasoning="Corrected reasoning")}
        )
        recorder.record({})
        path = tmp_path / "corrections.html"
        save_history_html(recorder.export_history(), path)
    page = browser.new_page()
    page.goto(path.as_uri())
    page.locator(".predicate .card-header").click()
    assert "Initial reasoning" in page.locator("#inspector").inner_text()
    page.locator("#timeline").fill("2")
    assert "Corrected reasoning" in page.locator("#inspector").inner_text()
    assert "Initial reasoning" not in page.locator("#inspector").inner_text()
    page.locator("#overview").click()
    page.locator(".trace-link").filter(has_text="Approved").click()
    assert "Corrected reasoning" in page.locator(".trace-step").inner_text()
    page.locator("#timeline").fill("0")
    page.locator("#inspector summary").click()
    page.locator(".trace-link").click()
    assert "Initial reasoning" in page.locator(".trace-step").inner_text()
    assert page.locator(".trace-step .badge").inner_text() == "No"
    page.locator(".predicate .card-header").click()
    assert "Initial reasoning" in page.locator("#inspector").inner_text()
    page.close()


def test_nested_groups_show_predicates_and_batch_highlights_together(
    browser: Any, tmp_path: Path, underwriting_policy: SRG
) -> None:
    srg = underwriting_policy
    first_batch = {"has_good_credit", "appraisal_supports_price"}
    with record_execution(
        ExecutionHistory.from_execution(SRGExecution(srg=srg))
    ) as recorder:
        recorder.record(
            {
                id_: Answer(is_met=True, reasoning="Confirmed together")
                for id_ in first_batch
            }
        )
        recorder.record(
            {"has_good_credit": Answer(is_met=False, reasoning="Corrected")}
        )
        recorder.record({})
        path = tmp_path / "groups.html"
        save_history_html(recorder.export_history(), path)
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    page.goto(path.as_uri())
    assert page.locator(".card").count() == len(srg.nodes)
    assert (
        page.locator("#predicate-board, .dependency-card, .expand-control").count() == 0
    )
    assert set(
        page.locator(".requirement.leaf").evaluate_all(
            "rows => rows.map(row => row.dataset.symbolId)"
        )
    ) == set(srg.predicates)
    borrower = page.get_by_role("region", name="Borrower risk", exact=True).first
    assert set(
        borrower.evaluate(
            "group => [...group.querySelectorAll(':scope > .requirement-children > .requirement')]"
            ".map(row => row.dataset.symbolId)"
        )
    ) == {"has_good_credit", "has_stable_income", "has_low_dti"}
    assert borrower.evaluate("node => getComputedStyle(node).borderTopStyle") == "solid"
    assert (
        borrower.locator(".requirement-children").first.evaluate(
            "node => getComputedStyle(node).borderLeftStyle"
        )
        == "solid"
    )
    assert (
        borrower.locator(".requirement.nested .requirement-rule").first.inner_text()
        == "ALL · Yes"
    )
    positions = page.locator(".card, .requirement").evaluate_all(
        "nodes => nodes.map(node => node.getBoundingClientRect().toJSON())"
    )
    for step, expected, credit_value in (
        (1, first_batch, "Yes"),
        (2, {"has_good_credit"}, "No"),
        (3, set(), "No"),
        (0, set(), "Unanswered"),
    ):
        page.locator("#timeline").fill(str(step))
        assert (
            set(
                page.locator(".requirement.leaf.changed").evaluate_all(
                    "rows => rows.map(row => row.dataset.symbolId)"
                )
            )
            == expected
        )
        credit_badges = page.locator(
            '.requirement.leaf[data-symbol-id="has_good_credit"] .badge'
        )
        assert credit_badges.count() > 1
        assert set(credit_badges.all_text_contents()) == {credit_value}
        assert positions == page.locator(".card, .requirement").evaluate_all(
            "nodes => nodes.map(node => node.getBoundingClientRect().toJSON())"
        )
    borrower.locator(".requirement.nested").first.click()
    assert page.locator("#inspector h2").inner_text() == "Borrower risk"
    page.locator("#timeline").fill("2")
    predicate = borrower.locator('.requirement.leaf[data-symbol-id="has_good_credit"]')
    predicate.focus()
    page.keyboard.press("Enter")
    assert predicate.evaluate("node => node === document.activeElement")
    assert "Corrected" in page.locator("#inspector").inner_text()
    assert (
        page.locator('.requirement.selected[data-symbol-id="has_good_credit"]').count()
        > 1
    )
    page.close()


def test_wide_replay_keeps_parallel_batches_visible_in_fit(
    browser: Any, tmp_path: Path
) -> None:
    recording = Path(__file__).parents[1] / "examples/data/medical-necessity/replay.json"
    history = load_history_file(recording)
    path = tmp_path / "medical-necessity.html"
    save_history_html(history, path)
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(path.as_uri())
    page.locator("#fit").click()
    assert page.locator("#follow").get_attribute("aria-pressed") == "false"
    assert page.locator(".card").count() == len(history.srg.nodes)
    assert page.locator(".card.predicate").count() == 4
    assert page.locator(".card.outcome").count() == 2
    assert set(page.locator(".card.outcome .card-title").all_text_contents()) == {
        "Approved",
        "Needs review",
    }
    overview = page.locator("#world").get_attribute("style")
    positions = page.locator(".card").evaluate_all(
        "cards => cards.map(c => [c.style.left, c.style.top, c.offsetHeight])"
    )
    for step in [*range(len(history.batches) + 1), 0]:
        page.locator("#timeline").fill(str(step))
        changed = set(
            page.locator(
                ".requirement.leaf.changed, .card.predicate.changed"
            ).evaluate_all("nodes => nodes.map(node => node.dataset.symbolId)")
        )
        assert changed == (set(history.batches[step - 1]) if step else set())
        assert page.locator("#world").get_attribute("style") == overview
        assert positions == page.locator(".card").evaluate_all(
            "cards => cards.map(c => [c.style.left, c.style.top, c.offsetHeight])"
        )
        assert page.locator(".card").evaluate_all("""cards => cards.every(card => {
            const bounds = card.getBoundingClientRect();
            const view = document.getElementById('viewport').getBoundingClientRect();
            return bounds.left >= view.left && bounds.right <= view.right
                && bounds.top >= view.top && bounds.bottom <= view.bottom;
        })""")
    page.locator("#timeline").fill(str(len(history.batches)))
    page.locator('.requirement.leaf[data-symbol-id="fracture"]').click()
    assert (
        "displaced subcapital femoral-neck fracture"
        in page.locator("#inspector").inner_text()
    )
    page.locator("#overview").click()
    assert page.locator("#run-status").inner_text() == "Decision resolved"
    assert page.locator(".trace-link").filter(has_text="Approved").count() == 3
    assert page.locator(".trace-link").filter(has_text="Needs review").count() == 1
    page.locator(".trace-link").filter(has_text="Needs review").click()
    assert page.locator(".trace-step").count() > 0
    page.locator("#follow").click()
    assert page.locator("#follow").get_attribute("aria-pressed") == "true"
    page.locator("#zoom-in").click()
    assert page.locator("#follow").get_attribute("aria-pressed") == "false"
    page.locator("#fit").click()
    assert page.locator("#world").get_attribute("style") == overview
    assert not errors
    page.close()
