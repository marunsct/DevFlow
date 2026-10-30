"""A deliberate change judged equivalent once is not raised, or asked about, again (behind `EQUIVALENT_MUTANTS_REMEMBERED`).

A change that behaves exactly as the original - `>=` for `>` on a value that is never
equal, a constant no caller can reach - can never be noticed by a test. The testing
role says so when it is asked (`mutation_guided.equivalent_because`) and the finding is
closed; but the verdict lived only in that one finding. The probe of the next sprint
attempt, or of the next sprint over the same file, chose the same change again, raised
it again, and spent another fix stage and the same reasoning to reach the same verdict.

With the switch on, the verdict is written down in the workspace's `.harness/` folder
(git-ignored, kept through reverts): the file, the line's text, and the operator with
what it was changed to. The line's text rather than its number: a fix that adds a line
above it moves it, and it is the same change. The probe leaves a remembered change out
before it counts its few changes per sprint, so the budget goes to changes still worth
asking about. A change is remembered only on a reason the fixer gave
(`mutation_guided.EQUIVALENT`); a change closed as a gap is not, since a better test
may yet notice it.

The fixer's verdict is also read in its usual spellings - "Equivalent mutant: ...",
"This is an equivalent change - ..." - not only as the single prefix the request names.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `EQUIVALENT_MUTANTS_REMEMBERED` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Where the verdicts are kept, relative to the workspace.
FILE = ".harness/equivalent_mutants.json"
#: The fixer's verdict in its usual spellings: "Equivalent: why", "Equivalent mutant - why",
#: "This is an equivalent change: why".
_SAYS_EQUIVALENT = re.compile(
    r"^\s*(?:this\s+(?:mutant\s+|change\s+)?is\s+(?:an?\s+)?|an?\s+)?equivalent(?:\s+(?:mutant|change|mutation))?\s*[:\-–—]\s*(?P<why>.+)$",
    re.I | re.S,
)


def enabled() -> bool:
    return is_on("EQUIVALENT_MUTANTS_REMEMBERED", ON_BY_DEFAULT)


def says_equivalent(said: str) -> str:
    """The reason in a verdict of "equivalent" in any of its usual spellings; "" when it is not one."""
    found = _SAYS_EQUIVALENT.match(str(said or ""))
    return found["why"] if found else ""


def key_of(site: dict, text: str | None = None) -> str:
    """The identity of a change: its file, its line's text and the operator with what it became."""
    line = " ".join(str((site.get("text") if text is None else text) or "").split())
    return "␟".join([str(site["file"]), line, str(site["original"]), str(site["replacement"])])


def _known(root: str | Path) -> dict[str, str]:
    try:
        data = json.loads((Path(root) / FILE).read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(root: str | Path, site: dict, why: str) -> None:
    """Write down that this change behaves as the original. Never raises."""
    try:
        known = _known(root)
        known[key_of(site)] = " ".join(str(why).split())[:400]
        path = Path(root) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known, indent=1, sort_keys=True), encoding="utf-8")
    except Exception:  # noqa: BLE001 - a verdict not kept is asked again, as before
        logger.debug("Could not keep an equivalent-mutant verdict", exc_info=True)


def remember(root: str | Path, defect: Any, why: str) -> None:
    """Write down the verdict on a mutation finding closed as equivalent; nothing when off or the finding names no change."""
    if not enabled():
        return
    from app.acceptance import mutation_guided

    site = mutation_guided.site_of(defect)
    if site is not None:
        record(root, site, why)


def is_known(root: str | Path, site: dict, text: str | None = None) -> bool:
    """Whether this change was judged equivalent before."""
    return key_of(site, text) in _known(root)


def without_the_known(root: Path, project: Path, candidates: list[dict]) -> list[dict]:
    """`candidates` (sites relative to `project`) without those judged equivalent before; all of them when off."""
    if not enabled():
        return candidates
    known = _known(root)
    if not known:
        return candidates
    lines: dict[str, list[str]] = {}
    kept = []
    for site in candidates:
        file = (project / site["file"]).relative_to(root).as_posix()
        if file not in lines:
            try:
                lines[file] = (root / file).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                lines[file] = []
        text = lines[file][site["line"] - 1] if 0 < site["line"] <= len(lines[file]) else ""
        if key_of({**site, "file": file}, text) not in known:
            kept.append(site)
    return kept


def why_known(root: str | Path, site: dict) -> str:
    return _known(root).get(key_of(site), "")


__all__: list[Any] = [
    "FILE", "ON_BY_DEFAULT", "enabled", "is_known", "key_of", "record", "remember", "says_equivalent", "why_known", "without_the_known",
]
