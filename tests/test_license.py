"""The project is Apache-2.0 licensed, and its Python and npm manifests say so.

npm always packs a package's own ``LICENSE``, so each package carries a copy of the
root file.
"""

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
LICENSE = "Apache-2.0"
PACKAGES = sorted(path.parent for path in ROOT.glob("packages/*/package.json"))
# SHA-256 of https://www.apache.org/licenses/LICENSE-2.0.txt
APACHE_2_0_TEXT = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def _license_text() -> str:
    path = ROOT / "LICENSE"
    assert path.exists(), "no LICENSE file at the repository root"
    return path.read_text(encoding="utf-8")


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _manifest(path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


def test_license_is_the_unmodified_apache_text_under_a_copyright_line() -> None:
    copyright_line, rest = _license_text().split("\n", 1)

    assert copyright_line == "Copyright 2026 Anterior, Inc."
    assert hashlib.sha256(rest.encode()).hexdigest() == APACHE_2_0_TEXT


def test_python_package_declares_the_license_and_ships_the_file() -> None:
    _license_text()
    pyproject = _pyproject()
    project = pyproject["project"]

    assert project.get("license") == LICENSE
    assert project.get("license-files") == ["LICENSE"]
    # License expressions need PEP 639 support, added in setuptools 77.
    assert "setuptools>=77.0" in pyproject["build-system"]["requires"]


def test_python_package_has_no_license_classifier() -> None:
    # PEP 639 forbids license classifiers next to a license expression.
    classifiers = _pyproject()["project"]["classifiers"]

    assert [c for c in classifiers if c.startswith("License ::")] == []


@pytest.mark.parametrize(
    "manifest",
    [ROOT / "package.json", *(package / "package.json" for package in PACKAGES)],
    ids=lambda path: str(path.relative_to(ROOT)),
)
def test_every_npm_manifest_declares_the_license(manifest: Path) -> None:
    declared = _manifest(manifest).get("license")

    assert declared == LICENSE


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_every_npm_package_ships_the_license_file(package: Path) -> None:
    copy = package / "LICENSE"

    assert copy.exists(), f"{package.name} has no LICENSE to pack"
    assert copy.read_text(encoding="utf-8") == _license_text()
