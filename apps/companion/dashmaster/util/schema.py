"""Helpers for loading JSON schemas and validating payloads."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "templates" / "$schema"


def load_schema(name: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / f"{name}.schema.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(document: dict[str, Any], *, schema_name: str) -> None:
    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema)
    try:
        validator.validate(document)
    except ValidationError as exc:  # pragma: no cover - pass through tests
        raise SchemaValidationError(exc) from exc


class SchemaValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, error: ValidationError) -> None:
        self.error = error
        super().__init__(error.message)

    @property
    def path(self) -> str:
        return ".".join(str(elem) for elem in self.error.path)
