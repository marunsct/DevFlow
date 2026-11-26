"""A quality score for what a run built, from the stored product alone (plan PQ.10).

The hidden tests, the quality tests and the run's own suite all check function. The product quality audit of
2026-11-25 read eight stored products and found what none of them measures: a dark scheme whose main text was
1.09:1 on its background, controls styled by classes no element carries, a token stylesheet the page never loads, a
schema twelve fields short of the one the specification adopted, two error shapes in one service. Without a number,
no change aimed at those can be kept or parked under the Measure/Fix rule, so this is the number. It changes nothing
in a run: it reads the product and the specification, calls no model and runs nothing.

Three parts, each scored 0-100 as the share of its checks that pass (a check that does not apply is left out), and
each check printed with the lines that decided it:

- interface (a product with a page): a stylesheet is loaded; every stylesheet is loaded; no style rule styles a class
  or id nothing uses; no text/background pair declared in a stylesheet falls under the contrast minimum, in each
  colour scheme the stylesheet declares; no raw colour where the product has colour tokens; every field has a label;
  the page has words for an empty list, a request in flight and a failure; no focus outline removed without a
  replacement.
- data (a specification with stored records): the fields its domain model gives each record are declared
  (`app.analysis.schema_conformance`), ids of the stated kind, fields called unique declared unique, an index when
  the specification asks for one, migrations when it asks for them.
- service (code that answers with error statuses): one error shape, the specification's when it states one; no 500
  for a client's fault; a refusal the code raises answered 403 somewhere. And, wherever a manifest declares packages
  for development only, no product file imports one (`app.analysis.development_packages`): an install for running
  leaves them out, so the product fails at start.

Counted, not scored: comment lines in product code that are the model's deliberation left behind ("Let's assume...",
"Looking at the spec...", `deliberation_lines`).

Stack-agnostic: what each language spells differently is a small table here or in `schema_conformance`.

    python -m app.analysis.product_quality <workspace | project | run-id> [--json]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from app.analysis import schema_conformance as conformance

# --------------------------------------------------------------------------------------------------------------
# The result.
# --------------------------------------------------------------------------------------------------------------


@dataclass
class Check:
    """One check: its share passed (0..1, None when it does not apply), a one-line result, and its evidence."""

    name: str
    passed: float | None
    result: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class Part:
    name: str
    checks: list[Check] = field(default_factory=list)

    @property
    def score(self) -> float | None:
        applied = [c.passed for c in self.checks if c.passed is not None]
        return round(100 * sum(applied) / len(applied), 1) if applied else None


@dataclass
class QualityScore:
    product: str
    parts: list[Part]
    counts: dict[str, int | str]

    @property
    def overall(self) -> float | None:
        scores = [p.score for p in self.parts if p.score is not None]
        return round(sum(scores) / len(scores), 1) if scores else None

    def as_dict(self) -> dict:
        return {
            "product": self.product,
            "overall": self.overall,
            **{part.name: part.score for part in self.parts},
            "parts": {part.name: [asdict(check) for check in part.checks] for part in self.parts},
            "counts": self.counts,
        }

    def report(self, most_evidence: int = 8) -> str:
        lines = [f"quality of {self.product}", f"  overall: {_shown(self.overall)}"]
        for part in self.parts:
            lines.append(f"  {part.name}: {_shown(part.score)}")
            for check in part.checks:
                mark = "n/a " if check.passed is None else ("pass" if check.passed >= 1 else
                                                             "fail" if check.passed <= 0 else f"{check.passed:.2f}")
                lines.append(f"    [{mark}] {check.name}: {check.result}")
                lines += [f"           {line}" for line in check.evidence[:most_evidence]]
                if len(check.evidence) > most_evidence:
                    lines.append(f"           ... and {len(check.evidence) - most_evidence} more")
        lines.append("  counts: " + ", ".join(f"{k} {v}" for k, v in self.counts.items()))
        return "\n".join(lines)


def _shown(score: float | None) -> str:
    return "n/a" if score is None else f"{score:g}"


def _binary(name: str, failures: list[str], applies: bool = True, passed_text: str = "none", what: str = "") -> Check:
    if not applies:
        return Check(name, None, "does not apply")
    return Check(name, 0.0 if failures else 1.0, f"{len(failures)} {what}".strip() if failures else passed_text, failures)


# --------------------------------------------------------------------------------------------------------------
# Colours and stylesheets.
# --------------------------------------------------------------------------------------------------------------

#: Named colours a stylesheet commonly writes; the rest are rare enough to leave unread.
NAMED_COLOURS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "silver": (192, 192, 192), "navy": (0, 0, 128),
    "orange": (255, 165, 0), "yellow": (255, 255, 0), "purple": (128, 0, 128), "teal": (0, 128, 128),
    "maroon": (128, 0, 0), "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211), "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169), "whitesmoke": (245, 245, 245), "gainsboro": (220, 220, 220),
}
_HEX = re.compile(r"#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
_FUNCTION = re.compile(r"\b(rgba?|hsla?)\(([^)]*)\)", re.I)
_NAMED = re.compile(r"(?<![\w-])(" + "|".join(NAMED_COLOURS) + r")(?![\w-])", re.I)
_RAW_COLOUR = re.compile(_HEX.pattern + "|" + _FUNCTION.pattern + "|" + _NAMED.pattern, re.I)
#: Properties whose value is a colour a person sees as text, a surface or an edge.
_COLOUR_PROPERTIES = re.compile(
    r"^(?:color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?(?:-color)?|outline(?:-color)?|fill|stroke|"
    r"caret-color|accent-color|text-decoration-color|column-rule(?:-color)?)$", re.I)

Colour = tuple[float, float, float, float]


def parse_colour(value: str) -> Colour | None:
    """The first colour a CSS value names, as (r, g, b, alpha); None when it names none."""
    match = _RAW_COLOUR.search(value or "")
    if not match:
        return None
    text = match.group(0)
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
        return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), alpha
    function = _FUNCTION.match(text)
    if function:
        parts = [p for p in re.split(r"[\s,/]+", function.group(2).strip()) if p]
        if len(parts) < 3:
            return None

        def number(part: str, scale: float) -> float:
            return float(part[:-1]) * scale / 100 if part.endswith("%") else float(re.sub(r"[a-z]+$", "", part))

        try:
            alpha = number(parts[3], 1) if len(parts) > 3 else 1.0
            if function.group(1).lower().startswith("rgb"):
                return number(parts[0], 255), number(parts[1], 255), number(parts[2], 255), alpha
            return (*_hsl(number(parts[0], 360), number(parts[1], 1), number(parts[2], 1)), alpha)
        except ValueError:
            return None
    rgb = NAMED_COLOURS[text.lower()]
    return float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0


def _hsl(hue: float, saturation: float, lightness: float) -> tuple[float, float, float]:
    saturation, lightness = saturation if saturation <= 1 else saturation / 100, lightness if lightness <= 1 else lightness / 100
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    m = lightness - chroma / 2
    r, g, b = [(chroma, x, 0), (x, chroma, 0), (0, chroma, x), (0, x, chroma), (x, 0, chroma), (chroma, 0, x)][int(hue // 60) % 6]
    return (r + m) * 255, (g + m) * 255, (b + m) * 255


def _over(top: Colour, bottom: Colour) -> Colour:
    alpha = top[3]
    return (top[0] * alpha + bottom[0] * (1 - alpha), top[1] * alpha + bottom[1] * (1 - alpha),
            top[2] * alpha + bottom[2] * (1 - alpha), 1.0)


def contrast(one: Colour, other: Colour) -> float:
    """The WCAG contrast ratio of two opaque colours."""
    def luminance(colour: Colour) -> float:
        channels = []
        for channel in colour[:3]:
            c = channel / 255
            channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    lighter, darker = sorted((luminance(one), luminance(other)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@dataclass(frozen=True)
class Rule:
    selector: str
    declarations: tuple[tuple[str, str, int], ...]
    media: str
    file: str
    line: int


def css_rules(text: str, file: str = "") -> list[Rule]:
    """Every style rule of a stylesheet, with the media it sits under and each declaration's line."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text or "", flags=re.S)
    rules: list[Rule] = []

    def line_of(index: int) -> int:
        return text.count("\n", 0, index) + 1

    def matching(open_at: int, end: int) -> int:
        depth = 0
        for index in range(open_at, end):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    return index
        return end

    def parse(start: int, end: int, media: str) -> None:
        index = start
        while index < end:
            brace = text.find("{", index, end)
            if brace < 0:
                return
            prelude = text[index:brace].rsplit(";", 1)[-1].rsplit("}", 1)[-1].strip()
            close = matching(brace, end)
            if prelude.startswith(("@media", "@supports", "@layer", "@container")):
                parse(brace + 1, close, f"{media} {prelude}".strip())
            elif prelude and not prelude.startswith("@"):
                body_start = brace + 1
                declarations = []
                offset = body_start
                for piece in text[body_start:close].split(";"):
                    if ":" in piece and "{" not in piece:
                        name, value = piece.split(":", 1)
                        lead = len(piece) - len(piece.lstrip())
                        declarations.append((name.strip().lower(), value.strip(), line_of(offset + lead)))
                    offset += len(piece) + 1
                rules.append(Rule(" ".join(prelude.split()), tuple(declarations), media, file, line_of(brace)))
            index = close + 1

    parse(0, len(text), "")
    return rules


_DARK_MEDIA = re.compile(r"prefers-color-scheme\s*:\s*dark", re.I)
_LIGHT_MEDIA = re.compile(r"prefers-color-scheme\s*:\s*light", re.I)
_PAGE_SELECTORS = {":root", "html", "body"}
_DEFAULT_PAGE = {"light": (255.0, 255.0, 255.0, 1.0), "dark": (18.0, 18.0, 18.0, 1.0)}
_DEFAULT_TEXT = {"light": (0.0, 0.0, 0.0, 1.0), "dark": (255.0, 255.0, 255.0, 1.0)}


def _schemes(rules: list[Rule]) -> list[str]:
    dark = any(_DARK_MEDIA.search(r.media) for r in rules) or any(
        name == "color-scheme" and "dark" in value for r in rules for name, value, _ in r.declarations)
    return ["light", "dark"] if dark else ["light"]


def _in_scheme(rule: Rule, scheme: str) -> bool:
    return not (_DARK_MEDIA.search(rule.media) and scheme == "light") and not (_LIGHT_MEDIA.search(rule.media) and scheme == "dark")


def _variables(rules: list[Rule], scheme: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    for rule in sorted((r for r in rules if _in_scheme(r, scheme)), key=lambda r: bool(_DARK_MEDIA.search(r.media))):
        for name, value, _ in rule.declarations:
            if name.startswith("--"):
                variables[name] = value
    return variables


def _resolve(value: str, variables: dict[str, str], depth: int = 0) -> str:
    if depth > 6 or "var(" not in value:
        return value

    def one(match: re.Match) -> str:
        name, _, fallback = match.group(1).partition(",")
        return variables.get(name.strip(), fallback.strip())

    return _resolve(re.sub(r"var\(\s*(--[\w-]+(?:\s*,[^()]*)?)\)", one, value), variables, depth + 1)


def _merged(rules: list[Rule], scheme: str) -> dict[str, dict[str, tuple[str, str, int]]]:
    """Each selector's declarations in one scheme, later rules winning, as (value, file, line)."""
    merged: dict[str, dict[str, tuple[str, str, int]]] = {}
    for rule in sorted((r for r in rules if _in_scheme(r, scheme)), key=lambda r: bool(_DARK_MEDIA.search(r.media))):
        for selector in rule.selector.split(","):
            selector = selector.strip()
            for name, value, line in rule.declarations:
                merged.setdefault(selector, {})[name] = (value, rule.file, line)
    # A state of an element (`.save:hover`) keeps what the element itself declares.
    for selector in list(merged):
        base = _STATE.sub("", selector)
        if base != selector and base in merged:
            merged[selector] = {**merged[base], **merged[selector]}
    return merged


_STATE = re.compile(r":(?:hover|focus|focus-visible|focus-within|active|visited)\b")


def _background(declarations: dict[str, tuple[str, str, int]], variables: dict[str, str]) -> Colour | None:
    for name in ("background-color", "background"):
        if name in declarations:
            value = _resolve(declarations[name][0], variables)
            if "gradient" in value or "url(" in value:
                return None
            colour = parse_colour(value)
            if colour:
                return colour
    return None


def _large_text(declarations: dict[str, tuple[str, str, int]]) -> bool:
    size = (declarations.get("font-size") or ("",))[0]
    match = re.match(r"\s*([\d.]+)\s*(px|rem|em)", size)
    pixels = float(match.group(1)) * (1 if match.group(2) == "px" else 16) if match else 0
    weight = (declarations.get("font-weight") or ("",))[0]
    bold = weight.strip() in ("bold", "bolder") or (weight.strip().isdigit() and int(weight) >= 600)
    return pixels >= 24 or (bold and pixels >= 18.66)


#: Selectors whose text no contrast minimum applies to: a disabled control, a placeholder, a selection.
_EXEMPT = re.compile(r":disabled|\[disabled\]|::?placeholder|::?selection|sr-only|visually-hidden", re.I)


def contrast_failures(rules: list[Rule]) -> list[str]:
    """Each text/background pair a stylesheet declares that falls under the minimum, in each scheme it declares."""
    failures: dict[tuple[str, int, str], str] = {}
    for scheme in _schemes(rules):
        variables = _variables(rules, scheme)
        merged = _merged(rules, scheme)
        page = _DEFAULT_PAGE[scheme]
        text = _DEFAULT_TEXT[scheme]
        for selector in _PAGE_SELECTORS:
            found = _background(merged.get(selector, {}), variables)
            page = _over(found, page) if found else page
        for selector in _PAGE_SELECTORS:
            colour = parse_colour(_resolve(merged.get(selector, {}).get("color", ("",))[0], variables))
            text = _over(colour, page) if colour else text
        for selector, declarations in merged.items():
            if selector in _PAGE_SELECTORS or _EXEMPT.search(selector):
                continue
            own_background = _background(declarations, variables)
            if "color" not in declarations and own_background is None:
                continue
            background = _over(own_background, page) if own_background else page
            if "color" in declarations:
                value = _resolve(declarations["color"][0], variables)
                colour = parse_colour(value)
                if colour is None:
                    continue
                where = declarations["color"]
            else:
                colour, value = text, "the page's text colour"
                where = declarations.get("background-color") or declarations["background"]
            foreground = _over(colour, background)
            ratio = contrast(foreground, background)
            minimum = 3.0 if _large_text(declarations) else 4.5
            if ratio < minimum:
                key = (where[1], where[2], selector)
                failures.setdefault(key, f"{where[1]}:{where[2]} {selector}: {value} on {_hex(background)} "
                                         f"({scheme} scheme) is {ratio:.2f}:1, under {minimum:g}:1")
    return list(failures.values())


def _hex(colour: Colour) -> str:
    return "#" + "".join(f"{int(round(max(0, min(255, c)))):02x}" for c in colour[:3])


# --------------------------------------------------------------------------------------------------------------
# The interface part.
# --------------------------------------------------------------------------------------------------------------

_STYLE_SUFFIXES = {".css", ".scss", ".sass", ".less"}
_MARKUP_SUFFIXES = {".html", ".htm", ".vue", ".svelte", ".astro"}
_SCRIPT_MARKUP = {".jsx", ".tsx"}
_SELECTOR_NAME = re.compile(r"(?<![\w-])([.#])(-?[A-Za-z_][\w-]*)")
_FIELD_TAG = re.compile(r"<(input|textarea|select)\b", re.I)
_EMPTY_STATE = re.compile(
    r"empty[-_ ]?state|\bno \w+(?: \w+)? (?:yet|found|to show|here|saved|added)\b|\bnothing (?:here|yet|to show)\b|"
    r"add your first", re.I)
#: A page script that sends a request to a service.
_REQUEST = re.compile(r"\bfetch\s*\(|\baxios\b|XMLHttpRequest|\$\.(?:ajax|get|post)\b|\bhttpClient\b|\buseQuery\b", re.I)
#: A script that builds a page: it reaches the document, or renders markup.
_PAGE_SCRIPT = re.compile(r"\bdocument\.|\bwindow\.|\bcreateElement\b|\binnerHTML\b|\btextContent\b|\buseState\b|<[a-z]+[\s>/]")
_LOADING_STATE = re.compile(r"aria-busy|\bloading\b|\bspinner\b|\bsaving\b|please wait|\bisLoading\b|is-loading|\bbusy\b", re.I)
_ERROR_STATE = re.compile(r"role=[\"'{]*alert|aria-live|went wrong|could not|couldn't|failed to|try again|unable to", re.I)


def _strip_attribute_selectors(selector: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", selector)


def _tag_at(text: str, start: int) -> str:
    """The whole opening tag starting at `start`, braces and quotes held (a JSX attribute may hold `=>`)."""
    depth, quote = 0, ""
    for index in range(start, min(len(text), start + 4000)):
        char = text[index]
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ">" and depth <= 0:
            return text[start:index + 1]
    return text[start:start + 200]


#: Input kinds that take no text from a person, so need no label.
_NOT_A_FIELD = frozenset({"hidden", "submit", "reset", "image"})
#: Input kinds a person types into: a `value` attribute there is a default, not a label.
_TEXT_ENTRY = frozenset({"text", "email", "password", "search", "tel", "url", "number"})


def unlabelled_fields(path: Path, text: str, relative: str) -> tuple[int, list[str]]:
    """(fields, the unlabelled ones as evidence) of one markup file."""
    labelled_ids = set(re.findall(r"""(?:\bfor|htmlFor)\s*=\s*\{?\s*["'`]([^"'`]+)["'`]""", text))
    total, missing = 0, []
    for match in _FIELD_TAG.finditer(text):
        tag = _tag_at(text, match.start())
        kind = re.search(r"""\btype\s*=\s*\{?\s*["'`](\w+)""", tag)
        if kind and kind.group(1).lower() in _NOT_A_FIELD:
            continue
        # A control whose own `value` is its text (an input that sends or acts rather than takes text) is labelled
        # by that text.
        if kind and kind.group(1).lower() not in _TEXT_ENTRY and re.search(r"""\bvalue\s*=""", tag):
            continue
        total += 1
        ident = re.search(r"""\bid\s*=\s*\{?\s*["'`]([^"'`]+)["'`]""", tag)
        before = text[:match.start()]
        inside_label = before.rfind("<label") > before.rfind("</label")
        if re.search(r"aria-label(?:ledby)?\s*=", tag, re.I) or inside_label or (ident and ident.group(1) in labelled_ids):
            continue
        missing.append(f"{relative}:{text.count(chr(10), 0, match.start()) + 1} {' '.join(tag.split())[:100]}")
    return total, missing


def _is_markup(path: Path, text: str) -> bool:
    return path.suffix.lower() in _MARKUP_SUFFIXES or (
        path.suffix.lower() in _SCRIPT_MARKUP and bool(re.search(r"return\s*\(?\s*<[A-Za-z]|<[a-z]+[\s>]", text)))


def interface_part(project: Path, sources: dict[Path, str]) -> tuple[Part, dict[str, int]]:
    """The interface checks, and the counts they read."""
    part = Part("interface")
    relative = {path: path.relative_to(project).as_posix() for path in sources}
    styles = {p: t for p, t in sources.items() if p.suffix.lower() in _STYLE_SUFFIXES}
    markup = {p: t for p, t in sources.items() if _is_markup(p, t)}
    scripts = {p: t for p, t in sources.items() if p.suffix.lower() not in _STYLE_SUFFIXES}
    counts = {"stylesheets": len(styles), "markup files": len(markup)}
    if not markup:
        part.checks.append(Check("a page to judge", None, "no markup in the product"))
        return part, counts
    page_text = "\n".join(scripts.values())
    # A stylesheet only another stylesheet imports is loaded too, as is one a page names.
    loaded = {p for p in styles if re.search(r"(?<![\w-])" + re.escape(p.name) + r"\b", page_text)
              or any(q != p and re.search(r"@import[^;]*" + re.escape(p.name), styles[q]) for q in styles)}
    unloaded = [relative[p] for p in styles if p not in loaded]
    part.checks.append(Check("a stylesheet styles the page", 1.0 if loaded else 0.0,
                             ", ".join(sorted(relative[p] for p in loaded)) or "no stylesheet is loaded by the page"))
    part.checks.append(_binary("every stylesheet is loaded", [f"{name}: no page or script loads it" for name in unloaded],
                               applies=bool(styles), what="stylesheet(s) nothing loads"))
    rules = [rule for p in loaded for rule in css_rules(styles[p], relative[p])]
    counts["style rules"] = len(rules)

    unused: dict[str, str] = {}
    for rule in rules:
        for kind, name in _SELECTOR_NAME.findall(_strip_attribute_selectors(rule.selector)):
            if re.fullmatch(r"[0-9a-fA-F]{3,8}", name) and kind == "#":
                continue
            if not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", page_text):
                unused.setdefault(f"{kind}{name}", f"{rule.file}:{rule.line} {kind}{name} (in `{rule.selector[:80]}`)")
    part.checks.append(_binary("style rules styling nothing", list(unused.values()), applies=bool(rules),
                               what="class(es)/id(s) no markup or script uses"))
    failures = contrast_failures(rules)
    part.checks.append(_binary("contrast of declared colours", failures, applies=bool(rules),
                               what="text/background pair(s) under the minimum"))

    tokens = any(name.startswith("--") and parse_colour(value) for p in styles for rule in css_rules(styles[p])
                 for name, value, _ in rule.declarations)
    raw = [f"{rule.file}:{line} {rule.selector[:60]} {{ {name}: {value} }}"
           for rule in rules for name, value, line in rule.declarations
           if _COLOUR_PROPERTIES.match(name) and "var(" not in value and _RAW_COLOUR.search(value)]
    part.checks.append(_binary("raw colours where colour tokens exist", raw, applies=tokens and bool(rules),
                               what="declaration(s) with a raw colour"))

    total, missing = 0, []
    for path, text in markup.items():
        count, unlabelled = unlabelled_fields(path, text, relative[path])
        total += count
        missing += unlabelled
    counts["fields"] = total
    part.checks.append(_binary("fields with a label", missing, applies=total > 0, what="field(s) without a label",
                               passed_text=f"all {total} labelled"))

    # What a person can read: the page's markup and the scripts that build it, not comments or a log line.
    markup_text = "\n".join(markup.values())
    page_scripts = {p: t for p, t in scripts.items() if p in markup or _PAGE_SCRIPT.search(t)
                    or re.search(r"(?<![\w-])" + re.escape(p.name) + r"\b", markup_text)}
    product_lines = [(relative[p], n, line) for p, t in page_scripts.items() for n, line in enumerate(t.splitlines(), 1)
                     if "console." not in line and "readyState" not in line and not _COMMENT.match(line)]
    requests = any(_REQUEST.search(line) for _, _, line in product_lines)
    for name, pattern, applies in (("words for an empty list", _EMPTY_STATE, True),
                                   ("words for a request in flight", _LOADING_STATE, requests),
                                   ("words for a failure", _ERROR_STATE, True)):
        found = [f"{file}:{n} {' '.join(line.split())[:100]}" for file, n, line in product_lines if pattern.search(line)]
        part.checks.append(Check(name, (1.0 if found else 0.0) if applies else None,
                                 ("present" if found else "none found") if applies else "the page sends no request",
                                 found[:3]))

    removed = []
    for rule in rules:
        values = {name: value for name, value, _ in rule.declarations}
        if re.match(r"^(?:none|0)\b", values.get("outline", "x")) and "box-shadow" not in values \
                and not any(n.startswith("outline-") and n != "outline-offset" for n in values):
            removed.append(f"{rule.file}:{rule.line} {rule.selector[:80]} {{ outline: {values['outline']} }}")
    part.checks.append(_binary("focus outline removed without a replacement", removed, applies=bool(rules),
                               what="rule(s)"))
    return part, counts


# --------------------------------------------------------------------------------------------------------------
# The data part.
# --------------------------------------------------------------------------------------------------------------

_INDEX_DECLARED = re.compile(
    r"(?i)\bcreate\s+(?:unique\s+)?index\b|\bindex\s*[=:]\s*true\b|@@?index\b|\bhasindex\b|\b(?:add_|create)index\b|"
    r"\.index\(|\bindex\s*\(|\bIndex\(")
_MIGRATION_PATH = re.compile(r"(?i)(?:^|/)(?:migrations?|alembic|migrate|db/migrate)(?:/|$)|(?:^|/)\d{3,}[_-][\w-]+\.sql$")
#: A specification asking for an index on its data ("indexes on owner_id", "an index on email", "notes are indexed by
#: owner"), not `index.html`, and not a sentence about what the database engine does: measured, a specification's
#: "SQLite provides ... indexed lookups for O(log n) access" was read as asking for one, and the product's quality
#: lost a quarter for an index nobody asked for - the only time this check failed in 580 scored runs.
_ASKS_FOR_AN_INDEX = r"\b(?:indexes (?:on|for)|indexed (?:on|by)|(?:is|are|be) indexed|an index (?:on|for)|index on)\b"
#: A specification asking for schema migrations ("Alembic migrations", "a migration script"), not "JWT migration".
_ASKS_FOR_MIGRATIONS = (r"\b(?:schema |database |db )?migrations\b|\bmigration (?:tool|script|file|path)s?\b|"
                        r"\b(?:alembic|flyway|liquibase)\b|\bmigrate\b")
_NEGATED = re.compile(r"\b(?:no|not|without|none|never|nor|deferred?|defers)\b", re.I)


def _asks_for(text: str, word: str) -> list[str]:
    """Sentences of the specification that ask for `word` (indexes, migrations), not those that rule it out."""
    asked = []
    for sentence in re.split(r"(?<=[.;])\s+|\n", text or ""):
        match = re.search(word, sentence, re.I)
        if match and not _NEGATED.search(sentence[: match.start()]):
            asked.append(" ".join(sentence.split())[:160])
    return asked


def data_part(project: Path, sources: dict[Path, str], specification: str, records: list) -> tuple[Part, dict[str, int]]:
    part = Part("data")
    stored = [r for r in records if r.stored]
    counts = {"records": len(stored), "specified fields": sum(len(r.fields) for r in stored)}
    if not stored:
        part.checks.append(Check("records the specification adopts", None, "the specification lists no stored record"))
        return part, counts
    code = {p: t for p, t in sources.items() if p.suffix.lower() not in _STYLE_SUFFIXES}
    result = conformance.compare(project, stored, code)
    built = sum(1 for _, _, declared in result.fields if declared)
    counts["declared fields"] = built
    part.checks.append(Check(
        "fields the domain model gives each record", built / len(result.fields) if result.fields else None,
        f"{built} of {len(result.fields)} declared",
        [f"{d.record}: {', '.join(d.missing)} not in {d.declared_at or 'the product'}"
         + (f" `{d.code_line[:60]}`" if d.code_line else "") for d in result.differences if d.missing]))
    if result.id_kinds:
        agree = sum(1 for _, _, ok in result.id_kinds if ok)
        part.checks.append(Check("ids of the kind stated", agree / len(result.id_kinds),
                                 f"{agree} of {len(result.id_kinds)}",
                                 [f"{name}: the specification says {kind}; the declaration gives an integer id"
                                  for name, kind, ok in result.id_kinds if not ok]))
    if result.unique:
        agree = sum(1 for _, _, ok in result.unique if ok)
        part.checks.append(Check("fields called unique declared unique", agree / len(result.unique),
                                 f"{agree} of {len(result.unique)}",
                                 [f"{record}.{name} is not declared unique" for record, name, ok in result.unique if not ok]))
    asked = _asks_for(specification, _ASKS_FOR_AN_INDEX)
    if asked:
        # A primary key's own index is not one the specification asked for.
        lines = [f"{project_relative(project, p)}:{n} {' '.join(line.split())[:90]}" for p, t in code.items()
                 for n, line in enumerate(t.splitlines(), 1)
                 if _INDEX_DECLARED.search(line) and not re.search(r"(?i)primary[_ ]?key", line)]
        part.checks.append(Check("an index, as the specification asks", 1.0 if lines else 0.0,
                                 f"{len(lines)} index declaration(s)" if lines else "none declared",
                                 (lines or [f"asked: {asked[0]}"])[:5]))
    asked = _asks_for(specification, _ASKS_FOR_MIGRATIONS)
    if asked:
        paths = sorted({project_relative(project, p) for p in conformance.product_source_files(project) if
                        _MIGRATION_PATH.search(project_relative(project, p))}
                       | {d.relative_to(project).as_posix() for d in _directories(project) if _MIGRATION_PATH.search(
                           d.relative_to(project).as_posix() + "/")})
        part.checks.append(Check("migrations, as the specification asks", 1.0 if paths else 0.0,
                                 f"{len(paths)} found" if paths else "none found",
                                 (paths or [f"asked: {asked[0]}"])[:5]))
    return part, counts


def _directories(project: Path) -> Iterable[Path]:
    from app.analysis.walk import directories_under
    from app.stacks.languages import NOT_THE_PRODUCT

    return directories_under(project, skip=NOT_THE_PRODUCT)


def project_relative(project: Path, path: Path) -> str:
    return path.relative_to(project).as_posix()


# --------------------------------------------------------------------------------------------------------------
# The service part.
# --------------------------------------------------------------------------------------------------------------

#: Spellings of a status by name, in the frameworks' own words, read as numbers.
STATUS_NAMES = {
    "badrequest": 400, "unauthorized": 401, "unauthorised": 401, "forbidden": 403, "forbid": 403, "notfound": 404,
    "methodnotallowed": 405, "conflict": 409, "gone": 410, "payloadtoolarge": 413, "unprocessableentity": 422,
    "unprocessablecontent": 422, "toomanyrequests": 429, "internalservererror": 500, "serviceunavailable": 503,
}
_STATUS_CONTEXT = re.compile(r"(?i)status|abort|raise|throw|reply|res\.|response|http|results?\.|json|send|problem|error")
_STATUS_NUMBER = re.compile(r"(?<![\w.#-])([45]\d\d)(?![\w.%-])")
_STATUS_NAME = re.compile(
    r"(?i)(?<![a-z])(?:status_?)?(bad_?request|unauthori[sz]ed|forbid(?:den)?|not_?found|method_?not_?allowed|conflict|"
    r"unprocessable_?(?:entity|content)|too_?many_?requests|internal_?server_?error|service_?unavailable)(?:result)?\b")
_COMMENT = re.compile(r"^\s*(?://|#|\*|/\*|--|<!--)")
_BODY_KEYS = re.compile(r"""\{\s*["']?([A-Za-z_]\w*)["']?\s*[:=](?!=)""")
_MORE_KEYS = re.compile(r"""[,{]\s*["']?([A-Za-z_]\w*)["']?\s*[:=](?!=)""")
_KEYWORD_BODY = re.compile(r"\b(detail|message|error|errors|error_code|code|title)\s*=(?!=)")
_PROBLEM = re.compile(r"\bProblem\(|ProblemDetails|application/problem\+json")
_CLIENT_FAULT = re.compile(r"(?i)permission|forbidden|not found|duplicate|already exists|integrity|unique constraint|not allowed")
_REFUSAL_RAISED = re.compile(
    r"\b(?:raise|throw)\s+(?:new\s+)?([A-Za-z_]*(?:Permission|Forbidden|NotAllowed|AccessDenied|NotOwner)[A-Za-z_]*)")
_SERVICE_SKIP = _STYLE_SUFFIXES | _MARKUP_SUFFIXES


def _statuses(line: str) -> list[int]:
    if _COMMENT.match(line) or not _STATUS_CONTEXT.search(line):
        return []
    found = [int(n) for n in _STATUS_NUMBER.findall(line)]
    found += [STATUS_NAMES[re.sub(r"_", "", m.lower()).removesuffix("result")] for m in _STATUS_NAME.findall(line)
              if re.sub(r"_", "", m.lower()) in STATUS_NAMES]
    return found


def _shape(window: str) -> tuple[str, ...] | None:
    if _PROBLEM.search(window):
        return ("problem details",)
    first = _BODY_KEYS.search(window)
    if first:
        start = first.start()
        depth, end = 0, len(window)
        for index in range(start, len(window)):
            depth += {"{": 1, "}": -1}.get(window[index], 0)
            if depth == 0:
                end = index
                break
        body = window[start:end + 1]
        top = re.sub(r"\{[^{}]*\}", "", body[1:])  # nested objects' keys are not the shape
        return tuple(sorted(set(_MORE_KEYS.findall("{" + top))))
    keyword = _KEYWORD_BODY.findall(window)
    return tuple(sorted(set(keyword))) if keyword else None


_DEFINITION = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+|export\s+|async\s+|static\s+|private\s+|public\s+)*"
                         r"(?:fn|def|function|func)\s+([A-Za-z_]\w*)")


def _helpers(code: dict[Path, str]) -> dict[str, tuple[str, ...]]:
    """The error shape each small function builds, for a status passed to a helper (`error_response(404, ...)`)."""
    shapes = {}
    for text in code.values():
        lines = text.splitlines()
        for number, line in enumerate(lines):
            definition = _DEFINITION.match(line)
            if definition and re.search(r"(?i)error|problem|fail|respon|reply|abort", definition.group(1)):
                shape = _shape("\n".join(lines[number: number + 10]))
                if shape:
                    shapes.setdefault(definition.group(1), shape)
    return shapes


def specification_error_shape(specification: str) -> tuple[str, ...] | None:
    """The keys of the error body the specification's API contract states, when it states one as JSON."""
    found: list[tuple[int, tuple[str, ...]]] = []
    for line in (specification or "").splitlines():
        if not re.search(r"\b[45]\d\d\b|error responses?|error body", line, re.I):
            continue
        for match in re.finditer(r"\{\s*\"[A-Za-z_]\w*\"\s*:[^{}]*\}", line):
            keys = tuple(sorted(set(re.findall(r"\"([A-Za-z_]\w*)\"\s*:", match.group(0)))))
            if not any(re.search(r"(?i)error|message|detail|code|problem|reason", key) for key in keys):
                continue
            # An error body: best where the line speaks of every error response, then where it follows "error".
            if re.search(r"(?i)error (?:responses?|bodies|body|shape|format)", line[: match.start()]):
                found.append((0, keys))
            elif re.search(r"(?i)error[^{]{0,60}$", line[: match.start()]):
                found.append((1, keys))
            elif any(re.search(r"(?i)error|detail|problem", key) for key in keys):
                found.append((2, keys))
    return min(found)[1] if found else None


def service_part(project: Path, sources: dict[Path, str], specification: str) -> tuple[Part, dict[str, int | str]]:
    part = Part("service")
    code = {p: t for p, t in sources.items() if p.suffix.lower() not in _SERVICE_SKIP}
    shapes: dict[tuple[str, ...], list[str]] = {}
    codes: set[int] = set()
    errors = 0
    client_as_500 = []
    helpers = _helpers(code)
    for path, text in code.items():
        lines = text.splitlines()
        relative = project_relative(project, path)
        for number, line in enumerate(lines):
            statuses = [s for s in _statuses(line) if s >= 400]
            if not statuses:
                continue
            errors += 1
            codes.update(statuses)
            shape = _shape("\n".join(lines[number: number + 4])) or next(
                (helpers[name] for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", line) if name in helpers), None)
            if shape:
                shapes.setdefault(shape, []).append(f"{relative}:{number + 1} {' '.join(line.split())[:100]}")
            if 500 in statuses and _CLIENT_FAULT.search("\n".join(lines[max(0, number - 2): number + 3])):
                client_as_500.append(f"{relative}:{number + 1} {' '.join(line.split())[:100]}")
    counts: dict[str, int | str] = {"error responses": errors, "status codes": " ".join(map(str, sorted(codes))) or "-"}
    if not errors:
        part.checks.append(Check("error responses", None, "no error status found in the code"))
        return part, counts
    evidence = [f"{{{', '.join(shape)}}} x{len(where)}, first at {where[0]}" for shape, where in shapes.items()]
    part.checks.append(Check("one error shape", (1.0 if len(shapes) <= 1 else 0.0) if shapes else None,
                             f"{len(shapes)} shape(s)", evidence))
    stated = specification_error_shape(specification)
    if stated and shapes:
        part.checks.append(Check("the error shape the specification states", 1.0 if set(shapes) == {stated} else 0.0,
                                 f"stated {{{', '.join(stated)}}}", evidence))
    part.checks.append(_binary("a client's fault answered 500", client_as_500, what="place(s)"))
    raised = sorted({f"{project_relative(project, p)}: raises {m}" for p, t in code.items()
                     for m in _REFUSAL_RAISED.findall(t)})
    part.checks.append(Check("a refusal the code raises answered 403", (1.0 if 403 in codes else 0.0) if raised else None,
                             ("403 answered" if 403 in codes else "no 403 anywhere") if raised else "no refusal raised",
                             raised[:5] if 403 not in codes else []))
    return part, counts


# --------------------------------------------------------------------------------------------------------------
# The whole score.
# --------------------------------------------------------------------------------------------------------------

_COMMENT_LINE = re.compile(r"^\s*(?://|#|/\*|\*|\*/|<!--|-->)")
#: Words of a model thinking aloud, not of a comment written for a reader of the code. Measured in a stored product: a
#: route handler carried 14 comment lines of "Spec says...", "Looking at spec examples, it seems...", "Let's assume
#: we return the first error for simplicity unless the test expects all".
_DELIBERATION = re.compile(
    r"(?i)(?<!\w)(?:let's|let me|let us|i think|i'll|i will|i need to|i'm not sure|we'll|we will|it seems|seems like|"
    r"looking at|wait,|hmm+|spec says|the spec(?:ification)? (?:says|expects|wants|lists)|unless the tests? expects?|"
    r"as per (?:the )?spec)(?!\w)")
#: Lines of a comment block that think aloud before the whole block counts as deliberation.
DELIBERATION_LINES_IN_A_BLOCK = 2


def deliberation_lines(sources: dict[Path, str]) -> tuple[int, list[str]]:
    """The comment lines of product code in blocks that read as deliberation (at least `DELIBERATION_LINES_IN_A_BLOCK`
    of a block's lines think aloud), and where each such block is."""
    total, where = 0, []
    for path, text in sources.items():
        lines = text.splitlines()
        block: list[int] = []
        for number in range(len(lines) + 1):
            if number < len(lines) and _COMMENT_LINE.match(lines[number]):
                block.append(number)
                continue
            if sum(1 for n in block if _DELIBERATION.search(lines[n])) >= DELIBERATION_LINES_IN_A_BLOCK:
                total += len(block)
                where.append(f"{path.name}:{block[0] + 1}-{block[-1] + 1}")
            block = []
    return total, where


def _documents(workspace: Path) -> str:
    texts = []
    for name in ("technical_specification.md", "product_intake.md", "acceptance_criteria.md"):
        path = workspace / "docs" / name
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texts)


def score(project: Path, specification: str = "", documents: str = "",
          harness_files: Iterable[str] = ()) -> QualityScore:
    """The quality score of the product in `project`, held to `specification` (the document's text); `harness_files`
    (paths under `project`) are the setup a stack pack keeps, not the product's own imports."""
    files = conformance.product_source_files(project)
    sources = {path: path.read_text(encoding="utf-8", errors="replace") for path in files}
    records = conformance.records_in(conformance.domain_model_lines(specification))
    interface, interface_counts = interface_part(project, sources)
    data, data_counts = data_part(project, sources, f"{specification}\n{documents}", records)
    service, service_counts = service_part(project, sources, specification)
    from app.analysis import development_packages

    kept = set(harness_files)
    imported, declaring = development_packages.imported_in(
        project, {path: text for path, text in sources.items() if project_relative(project, path) not in kept})
    service.checks.append(_binary("no development-only package imported by product code", [str(i) for i in imported],
                                  applies=bool(declaring), what="import(s)"))
    deliberation, _ = deliberation_lines(sources)
    code_lines = sum(1 for text in sources.values() for line in text.splitlines()
                     if line.strip() and not _COMMENT_LINE.match(line))
    counts: dict[str, int | str] = {"source files": len(sources), "code lines": code_lines,
                                    **interface_counts, **data_counts, **service_counts,
                                    "development-only imports": len(imported),
                                    "deliberation comment lines": deliberation}
    return QualityScore(project.name, [interface, data, service], counts)


def score_workspace(workspace: Path) -> QualityScore:
    """The score of a run's workspace: its pinned project, held to its `docs/technical_specification.md`."""
    pin = workspace / ".project-directory"
    project = workspace / pin.read_text().strip() if pin.is_file() and pin.read_text().strip() else workspace
    document = workspace / "docs" / "technical_specification.md"
    specification = document.read_text(encoding="utf-8", errors="replace") if document.is_file() else ""
    return score(project, specification, _documents(workspace), _the_pack_s_files(workspace, project))


def _the_pack_s_files(workspace: Path, project: Path) -> set[str]:
    """The files the run's stack pack keeps as it set them up, relative to `project`; none when no pack is recorded."""
    try:
        from app.stacks.contract import kept_paths

        within = project.relative_to(workspace).as_posix()
        return {path[len(within) + 1:] if within != "." and path.startswith(within + "/") else path
                for path in kept_paths(workspace)}
    except Exception:  # noqa: BLE001 - every file read as the product's
        return set()


def _workspace_of(argument: str) -> Path:
    path = Path(argument)
    if path.is_dir():
        return path
    import glob

    found = glob.glob(f"/app/data/workspaces/*/workspace-{argument}")
    if not found:
        raise SystemExit(f"no workspace for {argument}")
    return Path(found[0])


def main(argv: list[str]) -> int:
    arguments = [a for a in argv if not a.startswith("--")]
    if not arguments:
        print("usage: python -m app.analysis.product_quality <workspace | run-id> [--json]")
        return 2
    result = score_workspace(_workspace_of(arguments[0]))
    print(json.dumps(result.as_dict(), indent=2) if "--json" in argv else result.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
