"""Contract checks for the generated recursive AST models."""

from typing import Any

import pytest
from pydantic import ValidationError

from symbolic_reasoning.gen.py.ast import (
    AggregatorDefinition,
    AllExpression,
    NotExpression,
    PolicyContextDefinition,
    ReferenceExpression,
    SourceFile,
)


def test_nested_ast_round_trips_without_wrapper_fields() -> None:
    location = {
        "start": {"line": 0, "column": 0, "offset": 0},
        "end": {"line": 0, "column": 1, "offset": 1},
    }
    payload = {
        "type": "source_file",
        "definitions": [
            {
                "type": "policy_context_definition",
                "value": "Underwriting",
                "loc": location,
            },
            {
                "type": "aggregator_definition",
                "id": "eligible",
                "expression": {
                    "type": "all",
                    "args": [
                        {
                            "type": "not",
                            "expr": {"type": "reference", "id": "p", "loc": location},
                            "loc": location,
                        }
                    ],
                    "loc": location,
                },
                "loc": location,
            }
        ],
    }

    ast = SourceFile.model_validate(payload)
    context = ast.definitions[0].root
    assert isinstance(context, PolicyContextDefinition)
    assert context.value == "Underwriting"
    definition = ast.definitions[1].root
    assert isinstance(definition, AggregatorDefinition)
    expression = definition.expression.root
    assert isinstance(expression, AllExpression)
    negation = expression.args[0].root
    assert isinstance(negation, NotExpression)
    assert isinstance(negation.expr.root, ReferenceExpression)
    assert ast.model_dump(exclude_none=True) == payload


def test_unknown_definition_type_is_rejected() -> None:
    payload: dict[str, Any] = {
        "type": "source_file",
        "definitions": [
            {
                "type": "predicate_definition",
                "id": "p",
                "question": "Q",
                "loc": {
                    "start": {"line": 0, "column": 0, "offset": 0},
                    "end": {"line": 0, "column": 1, "offset": 1},
                },
            }
        ],
    }
    SourceFile.model_validate(payload)
    payload["definitions"][0]["type"] = "unknown"

    with pytest.raises(ValidationError) as error:
        SourceFile.model_validate(payload)

    assert any(
        item["type"] == "literal_error"
        and item["loc"] == ("definitions", 0, "PredicateDefinition", "type")
        for item in error.value.errors()
    )
