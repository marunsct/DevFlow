"""Whether a page was designed at all, by checks that need no eyes.

Nothing measured how a product looks. The acceptance suite, the milestone
review and the benchmark's hidden tests all check function, so a page in the
browser's own defaults passed every one of them. Measured over the last 26
stored products: 20 shipped the scaffold's stylesheet untouched by any stage -
a reset of box sizing, the font and the page width, and nothing designed.

Two checks a script can make without judging taste: whether anything styles the
page beyond the scaffold's reset, and - for a brief that asks for phones -
whether the page fits a phone's width. The harness's page probe measures the
second (`app.stacks.packs._javascript.page_check`); a reviewer that can see
judges the rest from its screenshots.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Product kinds whose interface is a page.
_A_PAGE = frozenset({"browser_app", "fullstack"})

#: Directories a product's own styles are never in.
_NOT_THE_PRODUCT = frozenset({"node_modules", "test-results", "dist", "build", ".harness", "coverage"})

#: A brief that asks for the product to work on small screens.
_SMALL_SCREENS = re.compile(
    r"\b(?:responsive|mobile|phones?|smartphones?|small[- ]screens?|tablets?|narrow (?:screens?|viewports?))\b",
    re.I,
)


def asks_for_small_screens(brief_text: str) -> bool:
    """Whether the brief asks for the product to work on a phone's screen."""
    return bool(_SMALL_SCREENS.search(brief_text or ""))


#: A sentence about something a person operates on a page.
_A_CONTROL = re.compile(
    r"\b(?:field|text ?area|box|button|checkbox|check box|link|menu|tab|switch|toggle|select|"
    r"drop-?down|input|control|radio|slider|combo ?box)e?s?\b",
    re.I,
)

#: The names a sentence gives: `labelled "Title"`, `named "All", "Active" and "Completed"`.
_GIVES_NAMES = re.compile(
    r"""\b(?:labell?ed|named|titled)\s+((?:["“][^"”\n]{1,60}["”](?:\s*(?:,|\band\b|\bor\b)\s*)*)+)""",
    re.I,
)
_A_QUOTED_NAME = re.compile(r"""["“]([^"”\n]{1,60})["”]""")


def controls_the_brief_names(brief_text: str) -> list[str]:
    """Every name the brief gives a control a person operates, in order, once each.

    Read from sentences that are about a control (a field, a box, a link ...)
    and give it a quoted name: `a text field labelled "Title"`, `three
    buttons named "All", "Active" and "Completed"`. A product that gives the
    control another name, or none, is not the product the brief describes - and
    a test that finds it some other way cannot tell the two apart.
    """
    names: list[str] = []
    for sentence in re.split(r"\n+|(?<=[.;!?])\s+", brief_text or ""):
        if not _A_CONTROL.search(sentence):
            continue
        for run in _GIVES_NAMES.finditer(sentence):
            for name in _A_QUOTED_NAME.findall(run.group(1)):
                name = name.strip()
                if name and name not in names:
                    names.append(name)
    return names


def _same(one: str, other: str) -> bool:
    return " ".join(one.split()) == " ".join(other.split())


def _the_product_s(base: Path, pattern: str) -> list[Path]:
    return [
        path for path in base.rglob(pattern)
        if path.is_file() and not any(part in _NOT_THE_PRODUCT for part in path.relative_to(base).parts)
    ]


def nobody_styled_it(repo_root: str | Path | None) -> str:
    """The scaffold's stylesheet when it is all that styles a page, else "". Never raises.

    Styled means any of: a stylesheet the scaffold did not write, the
    scaffold's own changed, or a `<style>` block in a page. A product that is
    not a page, or a workspace no pack scaffolded, is never called unstyled.
    """
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        if found is None:
            return ""
        pack, record = found
        if pack.kind not in _A_PAGE:
            return ""
        base = Path(repo_root) / str(record.get("project") or "")
        scaffolded = {path: text for path, text in pack.files.items() if path.endswith(".css")}
        if not scaffolded or not base.is_dir():
            return ""
        for sheet in _the_product_s(base, "*.css"):
            relative = sheet.relative_to(base).as_posix()
            if relative not in scaffolded:
                return ""
            if not _same(sheet.read_text(encoding="utf-8", errors="replace"), scaffolded[relative]):
                return ""
        for page in _the_product_s(base, "*.html"):
            if re.search(r"<style\b", page.read_text(encoding="utf-8", errors="replace"), re.I):
                return ""
        return f"{record.get('project')}/{sorted(scaffolded)[0]}"
    except Exception:  # noqa: BLE001 - a check that cannot be made says nothing
        return ""


__all__ = ["asks_for_small_screens", "controls_the_brief_names", "nobody_styled_it"]
