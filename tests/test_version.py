"""The Python package and the npm packages share one version."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_python_and_npm_packages_share_one_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    npm = {
        json.loads(path.read_text(encoding="utf-8"))["version"]
        for path in ROOT.glob("packages/*/package.json")
    }
    assert npm == {pyproject["project"]["version"]}
