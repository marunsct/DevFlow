"""The UI's types of the API are generated from the server's schema, and kept current (plan UI-0).

The run list read `documents` for months after the server called the field
`document_names`: the UI's types were written by hand. They are generated now,
and these tests fail when the server's schema moves and the files were not
written again (`ENV=development PYTHONPATH=src .venv/bin/python scripts/ui/openapi_schema.py`).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _generator():
    spec = importlib.util.spec_from_file_location("openapi_schema", ROOT / "scripts" / "ui" / "openapi_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_ui_holds_the_server_s_schema_as_it_is_now():
    generator = _generator()
    assert generator.SCHEMA.read_text() == generator.current_schema(), (
        "the server's API changed: run scripts/ui/openapi_schema.py and commit both files it writes"
    )


def test_the_ui_s_types_are_the_ones_generated_from_it():
    generator = _generator()
    assert generator.TYPES.read_text() == generator.typescript(generator.SCHEMA.read_text()), (
        "api.gen.ts was edited by hand or not written again: run scripts/ui/openapi_schema.py"
    )


def test_what_the_server_sends_is_always_there_and_what_it_takes_only_when_required():
    schema = {
        "paths": {
            "/runs": {
                "get": {"responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Run"}}}}}},
                "post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Start"}}}}, "responses": {}},
            }
        },
        "components": {
            "schemas": {
                "Run": {
                    "properties": {
                        "run_id": {"type": "string"},
                        "stage": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                        "gaps": {"type": "array", "items": {"$ref": "#/components/schemas/Gap"}},
                    },
                    "required": ["run_id"],
                },
                "Gap": {"properties": {"text": {"type": "string"}}},
                "Start": {
                    "properties": {
                        "mode": {"enum": ["fast", "thorough"]},
                        "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                    "required": ["mode"],
                },
            }
        },
    }

    types = _generator().typescript(json.dumps(schema))

    assert "  stage: string | null;" in types  # sent: a defaulted field is still in the JSON
    assert "  text: string;" in types  # reached from a response through a reference
    assert "  gaps: Gap[];" in types
    assert '  mode: "fast" | "thorough";' in types
    assert "  note?: string | null;" in types  # accepted: may be left out
