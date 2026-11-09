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
    from app.analysis.walk import files_under

    return [
        path for path in files_under(base, _NOT_THE_PRODUCT, pattern)
        if not any(part in _NOT_THE_PRODUCT for part in path.relative_to(base).parts)
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


def named_controls_disabled_on_load(brief_text: str, shows: str) -> list[str]:
    """The controls the brief names that the page, as it loads, shows disabled.

    `shows` is the page's accessibility tree as the page check records it
    (`- button "Name" [disabled]`). Measured on one run: the interface design
    disabled the brief's "add" control until its required field held text; the
    product refused nothing, because nothing could be tried, and the customer's
    check that an empty entry is refused timed out waiting for the control.
    """
    disabled = []
    for name in controls_the_brief_names(brief_text):
        quoted = f'"{name}"'
        if any(quoted in line and "[disabled" in line for line in (shows or "").splitlines()):
            disabled.append(name)
    return disabled


#: The product's own page and script files, where a control is marked or set disabled.
_PAGE_SOURCES = frozenset({".html", ".htm", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte"})
_NOT_ITS_OWN = frozenset({"tests", "test", "__tests__", "acceptance", "e2e", "spec"})
#: `disabled` as an attribute or property - `<button disabled>`, `.disabled = `, `disabled={...}`,
#: `setAttribute('disabled'` - and not `aria-disabled` or a longer word.
_DISABLES = re.compile(r"(?<![\w-])disabled(?![\w-])")


def where_controls_are_disabled(repo_root: str | Path | None, most: int = 8) -> list[str]:
    """`path:line: text` for each line of the product's page and script files that disables a control. Never raises.

    Measured on one run: the disabled-on-load defect named the control but no file, and three fixers in a row
    read it as "disable it in more cases" - each fix made the control disabled for blank text too, broke the
    product's own empty-entry tests and was reverted, and the run shipped with the control disabled.
    """
    try:
        base = Path(repo_root or "")
        if not base.is_dir():
            return []
        found: list[str] = []
        from app.analysis.walk import files_under

        for path in sorted(files_under(base, _NOT_THE_PRODUCT, "*", skip_hidden=True)):
            relative = path.relative_to(base)
            if path.suffix.lower() not in _PAGE_SOURCES or any(part in _NOT_ITS_OWN for part in relative.parts):
                continue
            if re.search(r"\.(?:spec|test)\.[a-z]+$", path.name):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _DISABLES.search(line):
                    found.append(f"{relative.as_posix()}:{number}: {line.strip()[:120]}")
                    if len(found) >= most:
                        return found
        return found
    except Exception:  # noqa: BLE001 - a hint that cannot be found says nothing
        return []


#: A control in the page check's accessibility tree: `- button "All (0)"`, its role and its name.
_A_SHOWN_CONTROL = re.compile(r'^\s*-\s+([a-z]+)\s+"([^"\n]{1,120})"', re.M)


def named_controls_renamed(brief_text: str, shows: str) -> list[tuple[str, str]]:
    """(the brief's name, the name the page gives it) for each control the page shows under another name.

    A control counts as renamed when no control on the page has the brief's name exactly and one has a name that
    holds it as a whole word: the brief's "All" shown as "All (0)". Measured on one run: the filters read "All (0)",
    "Active (0)" and "Completed (0)", the suite found them some other way, and every customer check that asked for
    "All", "Active" or "Completed" by name timed out. A name the page does not show at all - a control that appears
    only once there are records - is not judged.
    """
    shown = [(role, " ".join(name.split())) for role, name in _A_SHOWN_CONTROL.findall(shows or "")]
    renamed: list[tuple[str, str]] = []
    for name in controls_the_brief_names(brief_text):
        if any(_same(name, other) for _, other in shown):
            continue
        word = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])", re.I)
        holding = [other for _, other in shown if word.search(other)]
        if holding:
            renamed.append((name, holding[0]))
    return renamed


__all__ = [
    "asks_for_small_screens",
    "controls_the_brief_names",
    "named_controls_disabled_on_load",
    "named_controls_renamed",
    "where_controls_are_disabled",
    "nobody_styled_it",
]
