"""Ensure template JSON files satisfy their schemas."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..util.schema import validate

TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "templates"


@pytest.mark.parametrize(
    "filename", [
        ("layout", "layout.json"),
        ("rules", "rules.json"),
        ("schema", "schema.json"),
        ("calibration", "calibration.json"),
        ("board_map", "board_map.json"),
        ("config", "config.json"),
        ("birth", "birth.json"),
    ]
)
def test_template_valid(filename):
    schema_name, template_name = filename
    data = json.loads((TEMPLATE_DIR / template_name).read_text(encoding="utf-8"))
    validate(data, schema_name=schema_name)
