"""Run a local stdio server with .srg source or compiled JSON policies."""

import argparse
from pathlib import Path

from symbolic_reasoning import SRG, compile_srg_file

from .server import create_srg_mcp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--srg",
        action="append",
        nargs=2,
        metavar=("ID", "PATH"),
        required=True,
        help="Register .srg source or a compiled SRG JSON file under ID; repeat for multiple policies",
    )
    args = parser.parse_args()
    graphs: dict[str, SRG] = {}
    for srg_id, file_path in args.srg:
        if srg_id in graphs:
            parser.error(f"Duplicate SRG ID: {srg_id}")
        try:
            path = Path(file_path).expanduser()
            graphs[srg_id] = (
                compile_srg_file(path)
                if path.suffix.lower() == ".srg"
                else SRG.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError) as exc:
            parser.error(f"Cannot load SRG {srg_id} from {file_path}: {exc}")
    create_srg_mcp(srgs=graphs).run(transport="stdio")


if __name__ == "__main__":
    main()
