"""A browser product's screenshots scored on a fixed checklist at release (plan EV.2, behind `SCREENSHOT_RUBRIC`).

Every score the loop keeps is about function: the hidden tests, the suite,
the criteria. How a delivered page looks was seen only by a reviewer's
findings, never as a number a run could be compared on. With the switch on,
and only when the judgement model reads images, the release shows it the
page probe's screenshots with `CHECKLIST` and records a 1-5 score per item
and their mean - in `.harness/screenshot-rubric.json`, the transcript, and the
run's KPIs. It is a score, never a gate: nothing is held back by it.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, create_model

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `SCREENSHOT_RUBRIC` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Where the score is kept, in the workspace.
RUBRIC_FILE = ".harness/screenshot-rubric.json"
#: The checklist, the same for every product: (field, what a 5 looks like).
CHECKLIST = (
    ("layout", "content is aligned and spaced, nothing overlaps or is cut off, and it fits both widths"),
    ("contrast", "every text and control can be read against what is behind it"),
    ("empty_states", "a list or view with nothing in it says so and says what can be done next"),
    ("error_states", "a failure is shown in words a person understands, near what caused it"),
)


class Item(BaseModel):
    score: int = Field(ge=1, le=5, description="1 (absent or broken) to 5 (as described).")
    note: str = Field(default="", description="One line: what in which screenshot earned the score.")


Rubric = create_model("Rubric", **{name: (Item, ...) for name, _ in CHECKLIST})  # type: ignore[call-overload]


def enabled() -> bool:
    return is_on("SCREENSHOT_RUBRIC", ON_BY_DEFAULT)


def _request(shots: list[tuple[str, bytes]]) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    checklist = "\n".join(f"- `{name}`: 5 when {meaning}." for name, meaning in CHECKLIST)
    text = (
        "Score the page in these screenshots - " + " and ".join(d for d, _ in shots) + " - on each item "
        f"of this checklist, 1 to 5:\n{checklist}\nA state the screenshots do not show scores 1 with the "
        "note \"not shown\". Answer with one JSON object, one field per item, each "
        '{"score": n, "note": "..."}, and nothing else.'
    )
    images = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}}
              for _, data in shots]
    return [SystemMessage(content="You judge how a delivered page looks, against a fixed checklist."),
            HumanMessage(content=[{"type": "text", "text": text}, *images])]


def score(repo_root: str | Path, model: Any, run_id: str | None = None) -> dict[str, Any] | None:
    """The page's scores and their mean, recorded; None when off, unseen or unscored. Never raises."""
    if not enabled() or model is None:
        return None
    try:
        from app.agents.answered_in_parts import _read
        from app.agents.page_screenshots import _the_screenshots
        from app.models.vision import the_reviewer_reads_images

        shots = _the_screenshots(repo_root)
        if not shots or not the_reviewer_reads_images():
            return None
        from app.observability.direct_calls import config_for_this_run

        reply = model.invoke(_request(shots), **config_for_this_run("release"))
        content = getattr(reply, "content", "")
        text = content if isinstance(content, str) else "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content or [])
        rubric = _read(text, Rubric)
        if rubric is None:
            return None
        items = {name: getattr(rubric, name).model_dump() for name, _ in CHECKLIST}
        result = {"items": items, "mean": round(sum(i["score"] for i in items.values()) / len(items), 2),
                  "screenshots": len(shots)}
        target = Path(repo_root) / RUBRIC_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        from app.observability.transcript import record

        record(run_id, "release", "screenshot_rubric", mean=result["mean"], items=items)
        return result
    except Exception:  # noqa: BLE001 - a score never holds a release back
        logger.warning("Could not score the page's screenshots", exc_info=True)
        return None


def from_records(records: list[dict]) -> float | None:
    """The run's last recorded mean, for its KPIs."""
    means = [r.get("mean") for r in records if r.get("kind") == "screenshot_rubric" and r.get("mean") is not None]
    return means[-1] if means else None


__all__ = ["CHECKLIST", "ON_BY_DEFAULT", "RUBRIC_FILE", "Rubric", "enabled", "from_records", "score"]
