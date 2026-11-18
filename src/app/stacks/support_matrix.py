"""Which stacks and model tiers the harness supports, and which are experimental (deep review 2026-11-18, F1).

A customer install has no operator auditing every run. Before a run starts, its owner should know whether the stack
the brief asks for has been delivered reliably here, or is experimental. The evidence is the harness's scored runs
(hidden tests, never shown to the run); the KPI ledger and the scored-run records that hold it are the loop's, on the
machine that measures, not in a customer's data volume - so the evidence is stated here, in one place, as of the
date below, and changed by hand when new scored runs move a stack.

A stack is **supported** with at least `MOST_RUNS_FOR_SUPPORT` scored runs on a pack and a mean hidden-test score of
at least `SUPPORTED_FROM`; every other pack is **experimental**: it has a pack, its commands are verified, and too
few runs (or too low a score) say how reliably it delivers. The evidence was measured on a local model of the
"standard" class (a 35B mixture-of-experts model, 3B active); a model whose measured tier is weak is experimental on
every stack, and a strong one is held to the same table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUPPORTED, EXPERIMENTAL = "supported", "experimental"
#: The model tiers `app.models.guidance.tier_of` gives a diagnosed model.
TIERS = ("strong", "standard", "weak")
#: The least evidence that makes a stack supported.
MOST_RUNS_FOR_SUPPORT = 5
SUPPORTED_FROM = 0.9
#: When the evidence below was read from the scored runs.
EVIDENCE_AS_OF = "2026-11-18"


@dataclass(frozen=True)
class Evidence:
    """What the scored runs on one pack showed: the product family, how many runs, their mean hidden-test score."""

    family: str
    runs: int
    mean_hidden_score: float

    @property
    def supported(self) -> bool:
        return self.runs >= MOST_RUNS_FOR_SUPPORT and self.mean_hidden_score >= SUPPORTED_FROM


#: Scored runs per pack, from the harness's benchmark runs (hidden tests) up to `EVIDENCE_AS_OF`.
EVIDENCE: dict[str, Evidence] = {
    "python-http-api": Evidence("small HTTP services (notes, a tracker)", 94, 0.93),
    "python-cli": Evidence("a command-line program (word statistics)", 40, 0.91),
    "python-library": Evidence("a library (text utilities)", 26, 0.95),
    "fullstack-page-fastapi": Evidence("a page with its own service (bookmarks)", 28, 0.95),
    "node-http-api": Evidence("a small HTTP service (notes)", 12, 1.0),
    "node-hono-native-api": Evidence("a small HTTP service (notes)", 106, 0.93),
    "browser-javascript": Evidence("a browser app (a list of items)", 33, 0.98),
    "browser-react": Evidence("a browser app (a list of items)", 9, 1.0),
    "fullstack-node": Evidence("a page with its own service (bookmarks)", 14, 0.96),
    "csharp-aspnet-api": Evidence("a small HTTP service (notes)", 4, 1.0),
    "go-http-api": Evidence("a small HTTP service (notes)", 3, 1.0),
    "java-spring-api": Evidence("a small HTTP service (notes)", 5, 0.8),
    "php-slim-api": Evidence("a small HTTP service (notes)", 2, 1.0),
    "ruby-sinatra-api": Evidence("a small HTTP service (notes)", 3, 1.0),
    "rust-axum-api": Evidence("a small HTTP service (notes)", 6, 0.48),
}


def status(pack: str, tier: str = "") -> str:
    """Supported or experimental, for a pack and a model's measured tier ("" when the model was never diagnosed)."""
    found = EVIDENCE.get(pack)
    if found is None or not found.supported or tier == "weak":
        return EXPERIMENTAL
    return SUPPORTED


def matrix() -> list[dict[str, Any]]:
    """One row per stack pack: its language, what each model tier gets on it, and the evidence."""
    from app.stacks.packs import ALL_PACKS

    rows = []
    for pack in ALL_PACKS:
        found = EVIDENCE.get(pack.name)
        rows.append({
            "pack": pack.name, "title": pack.title, "language": getattr(pack, "language", "") or "",
            **{tier: status(pack.name, tier) for tier in TIERS},
            "evidence": (f"{found.runs} scored run(s) of {found.family}, mean hidden-test score "
                         f"{found.mean_hidden_score:.2f}" if found else "no scored runs yet"),
        })
    return rows


#: Languages a brief may ask for, as it would name them, with the language the packs record.
_NAMED = (
    (re.compile(r"\bpython\b", re.I), "python"),
    (re.compile(r"\btypescript\b", re.I), "typescript"),
    (re.compile(r"\bjavascript\b|\bnode(?:\.js)?\b", re.I), "javascript"),
    # "Go" only where it names a language: capitalised, after "in", or before what a language comes with.
    (re.compile(r"(?i:\bgolang\b)|\bin Go\b|\bGo\b(?= (?:1\.\d+|modules?|standard library|on|with|using|and|only)\b)"
                r"|^\W*Go\b", re.M), "go"),
    (re.compile(r"\brust\b", re.I), "rust"),
    (re.compile(r"\bjava\b(?!\s*script)", re.I), "java"),
    (re.compile(r"\bkotlin\b", re.I), "kotlin"),
    (re.compile(r"\bc#|\bcsharp\b|\.net\b|\basp\.net\b", re.I), "csharp"),
    (re.compile(r"\bruby\b|\brails\b", re.I), "ruby"),
    (re.compile(r"\bphp\b|\blaravel\b", re.I), "php"),
    (re.compile(r"\bswift\b", re.I), "swift"),
    (re.compile(r"\belixir\b|\bphoenix framework\b", re.I), "elixir"),
    (re.compile(r"\bscala\b", re.I), "scala"),
)


def _languages_supported() -> set[str]:
    """The languages with at least one supported pack."""
    from app.stacks.packs import ALL_PACKS

    return {str(getattr(p, "language", "") or "") for p in ALL_PACKS if status(p.name, "standard") == SUPPORTED}


def for_the_brief(brief: str, tier: str = "") -> dict[str, Any] | None:
    """What the brief's stated stack and the model's tier say before a run starts; None when nothing is experimental.

    The language is read from the brief's technical constraints (`brief_constraints.constraint_lines`), so a word in
    a feature's description ("go to the list") is not taken for a stack. A brief that names no language lets the run
    choose, and it prefers a pack.
    """
    from app.agents.brief_constraints import constraint_lines

    text = "\n".join(constraint_lines(brief or ""))
    named = [language for pattern, language in _NAMED if pattern.search(text)]
    supported = _languages_supported()
    outside = [language for language in dict.fromkeys(named) if language not in supported]
    if outside:
        return {"status": EXPERIMENTAL, "languages": outside,
                "said": (f"The brief asks for {', '.join(outside)}: experimental here - too few scored runs, or too "
                         f"low a score, say how reliably it delivers (evidence as of {EVIDENCE_AS_OF}). Python, "
                         "JavaScript and TypeScript services, programs and pages are supported.")}
    if tier == "weak":
        return {"status": EXPERIMENTAL, "languages": list(dict.fromkeys(named)),
                "said": "The model's measured tier is weak: every stack is experimental on it."}
    return None


def the_model_and_its_tier() -> tuple[str, str]:
    """The configured build model and its measured tier ("" when never diagnosed). Never raises."""
    try:
        from app.models import _runtime_settings
        from app.models.guidance import recorded

        model = str(getattr(_runtime_settings(), "model_name", "") or "")
        profile = recorded(model) if model else None
        return model, str(getattr(profile, "tier", "") or "")
    except Exception:  # noqa: BLE001 - the table without the model's tier
        return "", ""


__all__ = ["EVIDENCE", "EVIDENCE_AS_OF", "EXPERIMENTAL", "SUPPORTED", "TIERS", "Evidence", "for_the_brief", "matrix",
           "status", "the_model_and_its_tier"]
