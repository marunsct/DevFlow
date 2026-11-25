"""The rendered page as text facts, for a UI/UX specialist whose model cannot read images (plan SP.4).

The UI/UX specialist's sprint check (`app.agents.advice_review`) was shown the page only as screenshots, and only when
its model reads images (`app.models.vision`); on a build model that does not, it had no view of the page at all and
judged a stylesheet by reading it. Measured on one medium run: low-contrast text, a layout wider than a phone and form
fields with no label passed it.

The page check every browser suite run starts with (`app.stacks.packs._javascript.page_check`) already loads the page
in the harness's Playwright and keeps its screenshots. It now also measures, at a desktop's width and a phone's
(`PAGE_FACTS`): each text colour on its background with the contrast ratio and whether it is below WCAG AA, what sticks
out past the viewport, the stylesheet rules that match no element, the rules that take the focus outline away, the
controls the Tab key reaches with no outline or ring, and the form fields with no label - written to the report it
keeps (`PAGE_LOAD_REPORT`). Here that report becomes a bounded section of the specialist's request.

Always on (a quality fix): given only when the reviewer does not read images and the page check has measured a page;
absent when the page never started. Never raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

#: The whole section, at most this many characters: the accessibility tree is cut first.
MOST_CHARACTERS = 3_600

#: The section's heading.
HEADING = "--- The page, measured in a browser (you are not shown it) ---"


def _flat(text: Any) -> str:
    return " ".join(str(text or "").split())


def _the_report(repo_root: str | Path) -> dict[str, Any]:
    from app.stacks import contract
    from app.stacks.packs._javascript import PAGE_LOAD_REPORT

    record = contract.read(repo_root) or {}
    path = Path(repo_root) / str(record.get("project") or "") / PAGE_LOAD_REPORT
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _colours(facts: dict[str, Any]) -> list[str]:
    out = []
    for pair in facts.get("colours") or []:
        if not isinstance(pair, dict):
            continue
        line = (f"{pair.get('text')} on {pair.get('background')}: {pair.get('ratio')}:1 "
                f"({pair.get('count')} element(s))")
        if pair.get("below"):
            line += f" - BELOW WCAG AA (needs {pair.get('below')}:1), e.g. {_flat(pair.get('example'))}"
        out.append(line)
    return out


def _at_a_width(label: str, facts: Any) -> list[str]:
    if not isinstance(facts, dict):
        return []
    lines = [f"At {label} ({facts.get('width')}px):"]
    colours = _colours(facts)
    if colours:
        lines.append("- text colours on their backgrounds, with contrast ratios: " + "; ".join(colours))
    wider = int(facts.get("pageWider") or 0)
    sticking = [_flat(item) for item in facts.get("overflowing") or [] if _flat(item)]
    if wider or sticking:
        lines.append(f"- the page scrolls sideways by {wider}px" + (": " + "; ".join(sticking) if sticking else ""))
    else:
        lines.append("- nothing is wider than the viewport")
    return lines


def _for_the_whole_page(report: dict[str, Any]) -> list[str]:
    facts = report.get("facts") or {}
    desktop = facts.get("desktop") if isinstance(facts.get("desktop"), dict) else {}
    lines = []
    if desktop.get("rules"):
        examples = [_flat(item) for item in desktop.get("unmatchedExamples") or [] if _flat(item)]
        lines.append(
            f"Stylesheet rules that match no element as the page first loads: {desktop.get('unmatched', 0)} of "
            f"{desktop.get('rules')} (a rule for a state the page reaches later is expected here; one whose names "
            "the markup never uses is not)" + (": " + ", ".join(examples) if examples else "")
        )
    removed = [_flat(item) for item in desktop.get("outlineRemoved") or [] if _flat(item)]
    if removed:
        lines.append("Rules that take the focus outline away: " + ", ".join(removed))
    focus = [item for item in facts.get("focus") or [] if isinstance(item, dict)]
    if focus:
        unseen = [_flat(item.get("control")) for item in focus if not item.get("seen")]
        lines.append(
            f"Moving through the page with the Tab key reached {len(focus)} control(s); "
            + (f"with no outline or ring when focused: {', '.join(unseen)}" if unseen else "each showed an outline or a ring")
        )
    unlabelled = [_flat(item) for item in desktop.get("unlabelled") or [] if _flat(item)]
    if unlabelled:
        lines.append("Form fields with no label: " + "; ".join(unlabelled))
    layout = report.get("layout") or {}
    overlaps = [_flat(item) for item in layout.get("overlaps") or [] if _flat(item)]
    small = [_flat(item) for item in layout.get("smallTargets") or [] if _flat(item)]
    if overlaps:
        lines.append("Drawn over each other at a phone's width: " + "; ".join(overlaps))
    if small:
        lines.append("Too small to tap at a phone's width (under 24x24px): " + "; ".join(small))
    for rule in layout.get("accessibility") or []:
        if isinstance(rule, dict):
            lines.append(f"Accessibility check ({rule.get('impact')}): {_flat(rule.get('help'))} - "
                         f"{rule.get('count')} element(s)")
    return lines


def section(repo_root: str | Path, interface_design: Sequence[str] = ()) -> str:
    """The page's measured facts as a section of a request, or "" when the page check measured no page. Never raises."""
    try:
        report = _the_report(repo_root)
        facts = report.get("facts") or {}
        if not isinstance(facts, dict) or not (isinstance(facts.get("desktop"), dict) or isinstance(facts.get("phone"), dict)):
            return ""
        design = [_flat(line) for line in interface_design or () if _flat(line)]
        lines = [
            f"\n\n{HEADING}",
            "Your model is not shown images, so the page check of the suite's last run measured the page for you, "
            "loaded with nothing done on it:",
            *_at_a_width("a desktop's width", facts.get("desktop")),
            *_at_a_width("a phone's width", facts.get("phone")),
            *_for_the_whole_page(report),
        ]
        closing = (
            ("Judge these against the interface design in the specification:\n" + "\n".join(f"- {line}" for line in design) + "\n"
             if design else "")
            + "Text below WCAG AA, content wider than a phone, a field with no label, a focus that cannot be seen or "
            "a stylesheet whose rules miss the markup is a design problem: name the fact that shows it."
        )
        body = "\n".join(lines)
        tree = _flat_tree(report.get("shows"), (facts.get("phone") or {}).get("shows") if isinstance(facts.get("phone"), dict) else "")
        room = MOST_CHARACTERS - len(body) - len(closing) - 2
        if room < 0:
            body = body[:MOST_CHARACTERS - len(closing) - 2].rsplit("\n", 1)[0]
            tree = ""
        elif len(tree) > room:
            tree = tree[:max(room - 20, 0)].rsplit("\n", 1)[0] + ("\n(cut)" if room > 40 else "")
        return body + ("\n" + tree if tree.strip() else "") + "\n" + closing
    except Exception:  # noqa: BLE001 - no report, or one this cannot read: the review as it was
        return ""


def _flat_tree(desktop: Any, phone: Any) -> str:
    desktop, phone = str(desktop or "").strip(), str(phone or "").strip()
    if not desktop and not phone:
        return ""
    out = "What the page shows, as its accessibility tree:\n" + (desktop or phone)
    if phone and desktop and phone != desktop:
        out += "\nAt a phone's width it shows:\n" + phone
    return out


def with_the_page_facts(
    request: dict[str, Any], repo_root: str | Path, interface_design: Sequence[str] = ()
) -> dict[str, Any]:
    """`request` with the page's measured facts after its text, or `request` when there are none. Never raises."""
    try:
        messages = list(request.get("messages") or [])
        if not messages or not isinstance(messages[-1].get("content"), str):
            return request
        added = section(repo_root, interface_design)
        if not added:
            return request
        return {**request, "messages": [*messages[:-1], {**messages[-1], "content": messages[-1]["content"] + added}]}
    except Exception:  # noqa: BLE001
        return request


__all__ = ["HEADING", "MOST_CHARACTERS", "section", "with_the_page_facts"]
