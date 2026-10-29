"""CI workflows reference actions by commit and run with a read-only token by default."""

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).parents[1] / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_every_action_is_pinned_to_a_commit(workflow: Path) -> None:
    uses = re.findall(r"uses:\s*([^\s#]+)", workflow.read_text(encoding="utf-8"))

    assert uses
    unpinned = [ref for ref in uses if not re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref)]
    assert unpinned == []


def test_ci_token_is_read_only_by_default() -> None:
    ci = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    # The top-level block grants only contents: read, and no job widens it.
    assert re.search(r"^permissions:\n  contents: read\n\n", ci, re.MULTILINE)
    assert ci.count("permissions:") == 1
