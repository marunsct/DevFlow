"""Fast delivery writes the specification's core with the architect and the rest in parts at once.

Measured on one run: the architect's answer was one reply of 30,000-50,000
tokens, 8 to 14 minutes each, and five were cut off before they ended.
"""

from __future__ import annotations

import inspect
import json
import re
import threading
from types import SimpleNamespace

from app.agents.principal_architect import TechnicalSpecificationOutput
from app.graph import specification_parts, workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CORE = TechnicalSpecificationOutput(
    product_scope="Notes over HTTP.", file_plan=["notes-api/src/store.ts - keeps notes"],
    api_and_event_contracts=["POST /notes -> 201"], library_usage=["hono - new Hono()"],
)


class _Parts:
    def __init__(self):
        self.asked, self.lock, self.at_once, self.running = [], threading.Lock(), 0, 0

    def invoke(self, messages):
        text = messages[-1].content
        with self.lock:
            self.asked.append(text); self.running += 1; self.at_once = max(self.at_once, self.running)
        names = re.search(r"Its keys are exactly: ([^.]+)\.", text).group(1).split(", ")
        threading.Event().wait(0.05)
        with self.lock:
            self.running -= 1
        if "error_catalogue" in names:
            return SimpleNamespace(content="I could not do that.")
        return SimpleNamespace(content="```json\n" + json.dumps({n: [f"{n} line"] for n in names}) + "\n```")


def test_the_other_sections_are_written_at_once_from_the_core():
    model = _Parts()

    spec = specification_parts.with_the_parts_written(CORE, model, "--- Product intake ---\nNotes.")

    assert model.at_once == 3, "the three parts are asked side by side"
    assert spec.function_contracts == ["function_contracts line"] and spec.test_cases == ["test_cases line"]
    assert spec.error_catalogue == [], "a part that failed is left for the empty-section check"
    assert spec.file_plan == CORE.file_plan and spec.product_scope == CORE.product_scope
    assert "notes-api/src/store.ts - keeps notes" in model.asked[0]
    assert not BANNED.search(model.asked[0].split("--- The specification's core ---")[0])
    assert not BANNED.search(specification_parts.CORE_NOTE)


def test_the_architect_is_asked_for_the_core_only_in_fast_delivery_and_not_in_a_revision():
    source = inspect.getsource(workflow)
    node = source[source.index("    def principal_architect_node("):source.index("    def architecture_review_node(")]
    assert "in_parts = _fast_delivery() and not (required_changes and previous_specification is not None)" in node
    assert node.index("with_the_parts_written(") < node.index("_incomplete_specification_sections(")


def test_with_no_model_named_the_parts_are_written_on_the_deployment_s_own(monkeypatch):
    """A run on the build model only handed `None` here; every part failed on `None.invoke`."""
    import app.models as models

    built = _Parts()
    monkeypatch.setattr(models, "build_default_chat_model", lambda *a, **k: built)

    spec = specification_parts.with_the_parts_written(CORE, None, "--- Product intake ---\nNotes.")

    assert spec.function_contracts == ["function_contracts line"] and len(built.asked) == 3
