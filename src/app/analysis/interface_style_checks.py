"""How a page is styled, checked by a script at each sprint's checks, as defects for the interface's builder (plan PQ.5).

The product quality audit of 2026-11-25 read eight stored products and found, behind green suites: a dark scheme whose
title was 1.09:1 on its background, controls styled by classes no element carries, the pack's token stylesheet never
loaded, and `outline: none` with nothing in its place. The page check already measured some of it for a reviewer
(`app.agents.page_facts`) and the quality score reads the rest from the stored product
(`app.analysis.product_quality`); nothing turned either into work. This does, reusing both:

- the pack's token stylesheet is loaded by the page: its custom properties are declared on the rendered page (the page
  check's `declared`), else - an older page check - the stylesheet is named by the page's code;
- text on its background reaches WCAG AA, measured from the computed styles in both colour schemes (`colours` in the
  page check's light and dark facts); the light scheme's pairs are left to the accessibility check when it already
  reports contrast;
- every class and id a stylesheet styles is used by the markup, and every state class the page's code sets (toggled,
  or chosen by a condition) is styled;
- no raw colour in a stylesheet where the pack ships design tokens;
- no focus outline removed without a replacement.

Gating (severity `major`, raised every round while found): a token stylesheet the page does not load - the whole
designed floor (both schemes, focus ring, controls) is gone at once, and the fix is one import - and body text under
4.5:1 in either scheme - text a person cannot read, the 1.09:1 title. The rest is one bundled `minor` defect: each is
a real fault with a small fix, but none stops a person using the page, so it gets one fix and is then set aside as a
recorded risk (`set_aside_after_one_try`), never holding a sprint. Bounded: at most three defects, each with at most
`MOST_EVIDENCE` lines per check.

Always on (a quality fix). Never raises: a check that cannot be made says nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Lines of evidence kept per check.
MOST_EVIDENCE = 6

#: Product kinds whose interface is a page.
_A_PAGE = frozenset({"browser_app", "fullstack"})

#: How each defect begins. Its first sentence is the same each time it is raised (a round refreshes the open defect
#: rather than queueing a second), and the words before its first colon are its kind, which the page check's
#: resolution reads to tell whether it is still found.
TOKENS_NOT_LOADED = "Design tokens: the page does not load the stylesheet that declares them."
TEXT_UNREADABLE = "Text contrast: text on the page is under the WCAG AA minimum for body text."
STYLING_FAULTS = (
    "Styling faults: the page's stylesheets and markup disagree in ways a script can prove, none of them holding "
    "the sprint."
)

#: The reason a bundled styling defect is set aside after its one fix.
SET_ASIDE = ("A styling fault that does not stop anyone using the page, left after its one fix: recorded, not holding "
             "the sprint.")


@dataclass
class Found:
    """What the checks found on one page, each list already bounded."""

    tokens_sheet: str = ""
    tokens_not_loaded: str = ""
    body_text: list[str] = field(default_factory=list)
    body_text_where: list[str] = field(default_factory=list)
    large_text: list[str] = field(default_factory=list)
    unused: list[str] = field(default_factory=list)
    unstyled_states: list[str] = field(default_factory=list)
    raw_colours: list[str] = field(default_factory=list)
    outline_removed: list[str] = field(default_factory=list)

    def styling_faults(self) -> bool:
        return bool(self.large_text or self.unused or self.unstyled_states or self.raw_colours or self.outline_removed)


def _bounded(lines: list[str], most: int = MOST_EVIDENCE) -> list[str]:
    lines = list(dict.fromkeys(line for line in lines if line))
    return lines if len(lines) <= most else [*lines[:most], f"... and {len(lines) - most} more"]


# --------------------------------------------------------------------------------------------------------------------
# The token stylesheet.
# --------------------------------------------------------------------------------------------------------------------

_DECLARED_NAME = re.compile(r"(--[\w-]+)\s*:")


def token_sheet(pack: Any) -> tuple[str, frozenset[str]]:
    """(the pack's stylesheet that declares its design tokens, the token names), or ("", ∅) for a pack with none."""
    for path, text in sorted((getattr(pack, "files", None) or {}).items()):
        if not str(path).endswith(".css"):
            continue
        names = frozenset(_DECLARED_NAME.findall(str(text)))
        if names:
            return str(path), names
    return "", frozenset()


def _the_sheet_is_loaded(project: Path, sheet: str, names: frozenset[str], facts: dict[str, Any],
                         page_code: str) -> str:
    """Why the token stylesheet is not loaded, or "" when it is (or cannot be told)."""
    declared = None
    for key in ("desktop", "phone"):
        measured = facts.get(key)
        if isinstance(measured, dict) and isinstance(measured.get("declared"), list):
            declared = set(declared or set()) | {str(name) for name in measured["declared"]}
    if declared is not None:
        if declared & names:
            return ""
        gone = "" if (project / sheet).is_file() else f" `{sheet}` is no longer in the project."
        shown = sorted(names, key=lambda name: (not name.startswith("--color-"), name != "--color-text", name))[:4]
        return (f"None of the design tokens `{sheet}` declares ({', '.join(shown)} ...) is declared on the rendered "
                f"page.{gone}")
    if not (project / sheet).is_file():
        return f"`{sheet}` is no longer in the project, and nothing the page loads declares its tokens."
    if re.search(r"(?<![\w-])" + re.escape(Path(sheet).name) + r"\b", page_code):
        return ""
    return f"No page, script or configuration of the product names `{Path(sheet).name}`."


# --------------------------------------------------------------------------------------------------------------------
# Contrast, from the computed styles in both schemes.
# --------------------------------------------------------------------------------------------------------------------

def _contrast(facts: dict[str, Any], axe_reports_contrast: bool) -> tuple[list[str], list[str], list[str]]:
    """(body text under 4.5:1, large text under 3:1, the elements of the first) from the page check's colour pairs."""
    body, large, examples = [], [], []
    for scheme, key in (("light", "desktop"), ("dark", "dark")):
        if scheme == "light" and axe_reports_contrast:
            continue
        measured = facts.get(key)
        if not isinstance(measured, dict):
            continue
        for pair in measured.get("colours") or []:
            if not isinstance(pair, dict) or not pair.get("below"):
                continue
            needed = float(pair.get("below") or 0)
            example = " ".join(str(pair.get("example") or "").split())
            line = (f"{pair.get('text')} on {pair.get('background')} in the {scheme} scheme is {pair.get('ratio')}:1, "
                    f"needs {needed:g}:1 ({pair.get('count')} element(s), e.g. {example})")
            if needed >= 4.5:
                body.append(line)
                examples.append(example.split(" ", 1)[0])
            else:
                large.append(line)
    return body, large, examples


# --------------------------------------------------------------------------------------------------------------------
# State classes the page's code sets that no stylesheet styles.
# --------------------------------------------------------------------------------------------------------------------

_A_NAME = r"([A-Za-z_][\w-]*)"
#: A class the page's code sets on an element now and then: toggled, added, or chosen by a condition.
_SETS_A_STATE_CLASS = (
    re.compile(r"""classList\.(?:add|toggle|replace)\(\s*(['"`])""" + _A_NAME + r"\1"),
    re.compile(r"""\bclass:""" + _A_NAME + r"""\s*=\s*\{"""),
    re.compile(r"""\[class\.""" + _A_NAME + r"""\]\s*="""),
)
#: `cond ? 'active' : ''` on a line about an element's classes.
_CHOSEN_CLASS = re.compile(r"""\?\s*(['"`])([\w-]*)\1\s*:\s*(['"`])([\w-]*)\3""")
_ABOUT_CLASSES = re.compile(r"class(?:Name|List)?\b|:class\b")
#: Vue's `:class="{ done: item.done, active: x }"`.
_VUE_CLASSES = re.compile(r""":class\s*=\s*["']\{([^}"']*)\}""")
_STYLE_SUFFIXES = frozenset({".css", ".scss", ".sass", ".less"})
_MARKUP_SUFFIXES = frozenset({".html", ".htm", ".vue", ".svelte", ".astro"})


def unstyled_state_classes(sources: dict[Path, str], base: Path) -> list[str]:
    """`file:line: the class` for each class the page's code sets on an element now and then that no stylesheet styles.

    Measured in a stored product: the filter controls were given `active` when chosen, no rule styled `.active`, and
    the chosen filter looked like the others.
    """
    styles = "\n".join(text for path, text in sources.items()
                       if path.suffix.lower() in _STYLE_SUFFIXES or path.suffix.lower() in _MARKUP_SUFFIXES)
    found: dict[str, str] = {}
    for path, text in sources.items():
        if path.suffix.lower() in _STYLE_SUFFIXES:
            continue
        relative = path.relative_to(base).as_posix()
        for number, line in enumerate(text.splitlines(), 1):
            names = [match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
                     for pattern in _SETS_A_STATE_CLASS for match in pattern.finditer(line)]
            if _ABOUT_CLASSES.search(line):
                for match in _CHOSEN_CLASS.finditer(line):
                    names += [name for name in (match.group(2), match.group(4)) if re.fullmatch(_A_NAME, name)]
            for block in _VUE_CLASSES.findall(line):
                names += re.findall(r"""['"]?""" + _A_NAME + r"""['"]?\s*:""", block)
            for name in names:
                if name and name not in found and not re.search(r"\." + re.escape(name) + r"(?![\w-])", styles):
                    found[name] = f"{relative}:{number}: sets `{name}`; no stylesheet styles `.{name}`"
    return list(found.values())


# --------------------------------------------------------------------------------------------------------------------
# All of it, for one workspace.
# --------------------------------------------------------------------------------------------------------------------

def _the_page_product(repo_root: str | Path) -> tuple[Any, Path] | None:
    """(the pack, the project folder) of a workspace whose product is a page; None for any other."""
    from app.stacks import contract

    found = contract.the_pack(repo_root)
    if found is None:
        return None
    pack, record = found
    if getattr(pack, "kind", "") not in _A_PAGE:
        return None
    project = Path(repo_root) / str(record.get("project") or "")
    return (pack, project) if project.is_dir() else None


def findings(repo_root: str | Path, accessibility: Any = ()) -> Found:
    """What the checks find on the workspace's page product; an empty `Found` when it is not one. Never raises.

    `accessibility` is the page check's accessibility findings, so the light scheme's contrast is not reported twice.
    """
    found = Found()
    try:
        located = _the_page_product(repo_root)
        if located is None:
            return found
        pack, project = located
        from app.agents.page_facts import the_report
        from app.analysis import product_quality, schema_conformance

        try:
            report = the_report(repo_root)
        except Exception:  # noqa: BLE001 - no page check yet: what the files say
            report = {}
        facts = report.get("facts") if isinstance(report.get("facts"), dict) else {}
        sources = {path: path.read_text(encoding="utf-8", errors="replace")
                   for path in schema_conformance.product_source_files(project)}
        page_code = "\n".join(text for path, text in sources.items() if path.suffix.lower() not in _STYLE_SUFFIXES)
        within = project.relative_to(Path(repo_root)).as_posix()
        sheet, names = token_sheet(pack)
        if sheet:
            found.tokens_sheet = f"{within}/{sheet}" if within not in ("", ".") else sheet
            found.tokens_not_loaded = _the_sheet_is_loaded(project, sheet, names, facts, page_code)
        axe_contrast = any(isinstance(rule, dict) and rule.get("id") == "color-contrast" for rule in accessibility or ())
        body, large, examples = _contrast(facts, axe_contrast)
        found.body_text, found.large_text = _bounded(body), _bounded(large)
        if body:
            from app.analysis.interface_checks import where_selectors_are_defined

            found.body_text_where = where_selectors_are_defined(repo_root, examples, most=MOST_EVIDENCE)
        part, _ = product_quality.interface_part(project, sources)
        checks = {check.name: check for check in part.checks}

        def evidence(name: str) -> list[str]:
            """The check's failing lines, each `file:line ...` made workspace-relative."""
            check = checks.get(name)
            if check is None or check.passed is None or check.passed >= 1:
                return []
            return [f"{within}/{line}" if within not in ("", ".") and re.match(r"^[\w./-]+\.\w+:\d", line) else line
                    for line in check.evidence]

        found.unused = _bounded(evidence("style rules styling nothing"))
        found.unstyled_states = _bounded(unstyled_state_classes(sources, Path(repo_root)))
        found.raw_colours = _bounded(evidence("raw colours where colour tokens exist")) if sheet else []
        unseen = [f"the Tab key reaches {item.get('control')} and shows no outline or ring"
                  for item in facts.get("focus") or [] if isinstance(item, dict) and not item.get("seen")]
        removed = evidence("focus outline removed without a replacement")
        found.outline_removed = _bounded(removed + unseen) if removed else []
    except Exception:  # noqa: BLE001 - a check that cannot be made says nothing
        return found
    return found


def defects(repo_root: str | Path, accessibility: Any = ()) -> list[Any]:
    """The defects for the interface's builder: at most two gating ones and one bundled styling defect. Never raises."""
    from app.agents.specialists import ReportedDefect

    found = findings(repo_root, accessibility)
    out = []
    try:
        if found.tokens_not_loaded:
            out.append(ReportedDefect(
                description=f"{TOKENS_NOT_LOADED} {found.tokens_not_loaded}",
                severity="major",
                reproduction_steps=("Load the page: the harness's page check lists the custom properties its "
                                    "stylesheets declare, and none of the design tokens is among them."),
                expected_behavior=(
                    f"The page loads `{found.tokens_sheet}` (the scaffold's import or link to it, kept or restored), "
                    "and the product's own styles use its tokens - var(--color-text), var(--color-bg) - rather than a "
                    "second set of raw colours. Without it the page has no dark scheme, no focus ring and no styled "
                    "controls."),
                actual_behavior=found.tokens_not_loaded,
                affected_files=[found.tokens_sheet],
                owner="ui_ux",
                regression_test_required=False,
            ))
        if found.body_text:
            out.append(ReportedDefect(
                description=f"{TEXT_UNREADABLE} " + "; ".join(found.body_text[:2]),
                severity="major",
                reproduction_steps=("Load the page in each colour scheme: the harness's page check measures each "
                                    "text colour on its background from the computed styles."),
                expected_behavior=(
                    "Text of normal size reaches 4.5:1 on its background in the light and the dark scheme. Take the "
                    "colours from the design tokens (var(--color-text), var(--color-muted) on var(--color-bg) or "
                    "var(--color-surface)), which pass in both; a raw colour does not follow the scheme."),
                actual_behavior="; ".join(found.body_text) + (
                    ". Where those elements are made and styled: " + "; ".join(found.body_text_where)
                    if found.body_text_where else ""),
                affected_files=sorted({line.split(":", 1)[0] for line in found.body_text_where}),
                owner="ui_ux",
                regression_test_required=False,
            ))
        if found.styling_faults():
            sections = [
                ("Large text under 3:1", found.large_text),
                ("Classes and ids a stylesheet styles that no markup or code uses", found.unused),
                ("Classes the page's code sets that no stylesheet styles", found.unstyled_states),
                ("Raw colours where the design tokens should be used", found.raw_colours),
                ("Focus outlines removed with nothing in their place", found.outline_removed),
            ]
            listed = " ".join(f"{title}: " + "; ".join(lines) + "." for title, lines in sections if lines)
            files = sorted({line.split(":", 1)[0] for _, lines in sections for line in lines
                            if re.match(r"^[\w./-]+\.\w+:\d", line)})
            out.append(ReportedDefect(
                description=STYLING_FAULTS + " " + "; ".join(title.lower() for title, lines in sections if lines) + ".",
                severity="minor",
                reproduction_steps=("Read the product's stylesheets beside its markup and code, and load the page: "
                                    "the harness checks each without a model."),
                expected_behavior=(
                    "Each class or id a stylesheet styles is one the markup uses, and each class the code sets on an "
                    "element is styled - rename one side to match the other. Colours are the design tokens' "
                    "var(--color-...) names, not raw values. A rule that takes the focus outline away gives one in its "
                    "place (a border colour or a box-shadow on :focus-visible). Large text reaches 3:1."),
                actual_behavior=listed[:2000],
                affected_files=files,
                owner="ui_ux",
                regression_test_required=False,
            ))
    except Exception:  # noqa: BLE001
        return out
    return out


def states_defect(state: Any, repo_root: str | Path) -> list[Any]:
    """With `INTERFACE_STATES_AS_CRITERIA` on: a defect when the built page does not show a state the specification
    names (`Empty:`, `Busy:`, `Failed:`), from the page check's report and the page's code (plan PQ.8). Never raises."""
    try:
        from app.agents import interface_states

        if not interface_states.enabled():
            return []
        design = getattr(state.get("technical_specification"), "interface_design", None) or []
        if not interface_states.state_lines(design):
            return []
        located = _the_page_product(repo_root)
        if located is None:
            return []
        _, project = located
        from app.agents.page_facts import the_report
        from app.analysis import schema_conformance

        report = the_report(repo_root)
        code = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                         for path in schema_conformance.product_source_files(project)
                         if path.suffix.lower() not in _STYLE_SUFFIXES)
        missing = interface_states.not_shown(design, report, code)
        if not missing:
            return []
        from app.agents.specialists import ReportedDefect

        return [ReportedDefect(
            description=STATES_NOT_SHOWN + " " + "; ".join(missing),
            severity="major",
            reproduction_steps=("Load the page with nothing in it, with the requests it makes held back, and with "
                                "them failing: the harness's page check records what it shows each time."),
            expected_behavior=(
                "The page shows each state the specification's interface design names, with its role and its words: "
                "an element of its own outside any list of records, present while the state lasts and gone after."),
            actual_behavior="; ".join(missing),
            affected_files=[],
            owner="ui_ux",
            regression_test_required=False,
        )]
    except Exception:  # noqa: BLE001 - a check that cannot be made says nothing
        return []


#: How the interface-states defect begins.
STATES_NOT_SHOWN = "Interface states: the page does not show a state the specification names."


def set_aside_after_one_try(cycle: Any, measured: list[Any]) -> tuple[Any, list[Any]]:
    """`cycle` with each open styling-faults defect this round raised again after a failed fix accepted as a risk, and
    `measured` without them: the bundled defect is not gating. Any other defect, or a first raising, is left alone."""
    from app.sprint import accept_risk, failed_fix_tries

    again = {" ".join(str(getattr(item, "description", "") or "").split()) for item in measured
             if str(getattr(item, "description", "") or "").startswith(STYLING_FAULTS)}
    if not again:
        return cycle, measured
    set_aside = set()
    for index, defect in enumerate(list(getattr(cycle, "defects", None) or [])):
        text = " ".join(str(defect.description or "").split())
        if defect.status != "open" or text not in again or failed_fix_tries(cycle, index) < 1:
            continue
        cycle = accept_risk(cycle, index, reason=SET_ASIDE)
        set_aside.add(text)
    return cycle, [item for item in measured
                   if " ".join(str(getattr(item, "description", "") or "").split()) not in set_aside]


__all__ = [
    "MOST_EVIDENCE", "SET_ASIDE", "STATES_NOT_SHOWN", "STYLING_FAULTS", "TEXT_UNREADABLE", "TOKENS_NOT_LOADED",
    "Found", "defects", "findings", "set_aside_after_one_try", "states_defect", "token_sheet",
    "unstyled_state_classes",
]
