"""Export execution histories as self-contained HTML with batch playback."""

from __future__ import annotations

import argparse
import json
import webbrowser
from html import escape
from importlib.resources import files
from pathlib import Path
from typing import Any

from symbolic_reasoning.gen.py.srg import Edge
from symbolic_reasoning.models import (
    SRGExecution,
    evaluate_symbol,
    is_resolved,
    reasoning_trace,
)
from symbolic_reasoning.recording import ExecutionHistory, load_history_file
from symbolic_reasoning.solvers.solver import apply_answers


def _history_data(history: ExecutionHistory) -> dict[str, Any]:
    """Build per-step verdicts, reachability, and reasoning traces for a history."""
    srg = history.srg
    outgoing: dict[str, list[tuple[str, Edge]]] = {key: [] for key in srg.nodes}
    for edge_id, edge in srg.edges.items():
        outgoing[edge.source].append((edge_id, edge))
    frames = []
    execution = SRGExecution(srg=srg, answers=dict(history.initial_answers))
    for step in range(len(history.batches) + 1):
        if step:
            execution = apply_answers(execution, history.batches[step - 1])
        verdicts = {
            key: evaluate_symbol(execution, key)
            for key in ("Root", *srg.predicates, *srg.aggregators, *srg.outcomes)
        }
        reached, taken = {"Root"}, []
        pending = ["Root"]
        while pending:
            node_id = pending.pop()
            verdict = verdicts[srg.nodes[node_id].item_id]
            for edge_id, edge in outgoing[node_id]:
                if verdict is not None and verdict == edge.condition:
                    taken.append(edge_id)
                    if edge.target not in reached:
                        reached.add(edge.target)
                        pending.append(edge.target)
        resolved = is_resolved(execution)
        trace = reasoning_trace(execution) if resolved else None
        frames.append(
            {
                "applied": list(history.batches[step - 1]) if step else [],
                "verdicts": verdicts,
                "reached": sorted(reached),
                "taken": taken,
                "resolved": resolved,
                "trace": {
                    "outcome_paths": [
                        {
                            "outcome": path.outcome_id,
                            "steps": [item.predicate_id for item in path.steps],
                        }
                        for path in trace.outcome_paths
                    ],
                    "all_paths": [
                        {"steps": [item.predicate_id for item in path.steps]}
                        for path in trace.all_paths
                    ],
                }
                if trace is not None
                else None,
            }
        )
    recorded = history.model_dump(mode="json")
    return {
        "graph": recorded["srg"],
        "initial_answers": recorded["initial_answers"],
        "batches": recorded["batches"],
        "frames": frames,
    }


def _script_json(value: Any) -> str:
    # A JSON script element still obeys the HTML parser's </script> boundary.
    return (
        json.dumps(value, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _render_html(data: dict[str, Any], title: str) -> str:
    assets = files("symbolic_reasoning").joinpath("viewer_assets")
    replacements = {
        "TITLE": escape(title),
        "STYLE": assets.joinpath("viewer.css").read_text(encoding="utf-8"),
        "LAYOUT": assets.joinpath("vendor/dagre.min.js").read_text(encoding="utf-8"),
        "LICENSE": "\n".join(
            assets.joinpath(f"vendor/LICENSE.{name}").read_text(encoding="utf-8")
            for name in ("dagre", "graphlib")
        ),
        "DATA": _script_json(data),
        "SCRIPT": assets.joinpath("viewer.js").read_text(encoding="utf-8"),
    }
    # Splitting before substitution prevents user text from becoming a template marker.
    template = assets.joinpath("viewer.html").read_text(encoding="utf-8")
    parts = template.split("@@")
    return "".join(
        replacements[part] if index % 2 else part for index, part in enumerate(parts)
    )


def save_history_html(
    history: ExecutionHistory,
    file_path: str | Path,
    *,
    title: str = "SRG execution",
) -> None:
    """Write an interactive HTML history to a local file, replacing it if present.

    Embeds the graph, answers, reasoning, styles, and
    scripts. Parent directories must exist.
    """
    Path(file_path).write_text(
        _render_html(_history_data(history), title), encoding="utf-8"
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path, help="Recorded execution JSON file")
    parser.add_argument("-o", "--output", type=Path, default=Path("replay.html"))
    parser.add_argument("--title", default="SRG execution")
    parser.add_argument(
        "--open", action="store_true", help="Open the replay in your browser"
    )
    args = parser.parse_args()
    # samefile compares inodes, so ./x, symlinks and hard links are caught too.
    if args.output.exists() and args.output.samefile(args.history):
        parser.error(f"output {args.output} is the input recording")
    save_history_html(load_history_file(args.history), args.output, title=args.title)
    print(f"Replay saved to {args.output.resolve()}")
    if args.open:
        webbrowser.open(args.output.resolve().as_uri())


if __name__ == "__main__":
    _main()
