#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# Paths relative to repo root
REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "srg-schema-v1.json"
OUTPUT_PATH = REPO_ROOT / "src" / "symbolic_reasoning" / "gen" / "py" / "srg.py"


def generate_pydantic_models(
    schema_path: Path = SCHEMA_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    frozen: bool = False,
) -> None:
    """Generate Pydantic models from JSON Schema."""
    print("🐍 Generating Python types for SRG schema")
    print(f"   Schema: {schema_path}")
    print(f"   Output: {output_path}\n")
    print(f"Reading JSON Schema from: {schema_path}")

    if not schema_path.exists():
        print(f"❌ Schema file not found: {schema_path}")
        sys.exit(1)

    print("Converting to Pydantic models...")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    init_file = output_path.parent / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Generated Pydantic models from JSON Schema."""\n')

    # Run datamodel-codegen
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "datamodel-codegen",
                "--input",
                str(schema_path),
                "--output",
                str(output_path),
                "--input-file-type",
                "jsonschema",
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--use-schema-description",
                "--use-title-as-name",
                "--use-standard-collections",
                "--use-default",
                "--use-default-kwarg",
                "--use-union-operator",
                "--field-constraints",
                "--snake-case-field",
                *(
                    ["--enable-faux-immutability", "--use-generic-container-types"]
                    if frozen
                    else []
                ),
                "--disable-timestamp",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("❌ Error running datamodel-codegen:")
        print(e.stderr)
        sys.exit(1)

    with Path(output_path).open() as f:
        content = f.read()

    header = f'''"""
GENERATED FILE - DO NOT EDIT MANUALLY

This file is auto-generated from {schema_path.relative_to(REPO_ROOT)}
To regenerate, run: uv run python schemas/generate.py
"""

'''

    with Path(output_path).open("w") as f:
        f.write(header + content)

    print(f"✅ Generated Pydantic models at: {output_path}")


if __name__ == "__main__":
    try:
        generate_pydantic_models(frozen=True)
        generate_pydantic_models(
            REPO_ROOT / "schemas" / "srg-ast-v1.json",
            REPO_ROOT / "src" / "symbolic_reasoning" / "gen" / "py" / "ast.py",
        )
    except Exception as e:
        print(f"❌ Error generating Pydantic models: {e}")
        sys.exit(1)
