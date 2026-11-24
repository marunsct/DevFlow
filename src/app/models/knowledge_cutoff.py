"""When a model's training data ends: part of the model's profile, kept with its other capabilities (plan HK.7, LF.1302).

A model writes a library's API as its training data had it. A release line that began after that data ends is one it
cannot know: measured on Rust API changes, models scored 56% on APIs from before their cutoff and 33% after, and
retrieval of the release's own documentation raised the second to 48-58% (RustEvo2; GitChameleon 2.0 likewise, +10
points). The harness can only hand a builder the release's own API where it knows which libraries are newer than the
model, so the model's profile carries the date its training data ends (`capabilities` field `knowledge_cutoff`,
"YYYY-MM"), from, in this order:

1. the owner, on the settings page (the model's capabilities) - always wins;
2. the model card's own words ("knowledge cutoff: June 2024", "training data up to 2024-06");
3. else the card's repository creation month, as an upper bound: nothing after it can be in the training data.

`of_the_build_model` gives the cutoff of the model that builds and fixes the run: the one a caller passes, else the
run's pinned model, else the served one; "" when none is known, and then nothing is flagged.
"""

from __future__ import annotations

import re
from typing import Any

#: The capability field the date is kept under (`app.models.capabilities.FIELDS`).
FIELD = "knowledge_cutoff"

_MONTHS = {name: number for number, names in enumerate((
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
    ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
    ("dec", "december")), start=1) for name in names}

_A_DATE = r"(?:[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{4}[-/.]\d{1,2}|\d{4})"
#: How a card states it: "knowledge cutoff: June 2024", "training data cut-off date is 2024-06", "trained on data up
#: to March 2025", "pretraining data has a cutoff of December 2023".
_STATED = re.compile(
    r"(?:knowledge|training[ -]data|pre-?training(?:[ -]data)?|data)\s*(?:has\s+an?\s+)?cut[- ]?off(?:\s+date)?"
    r"\s*(?:is|was|of|:|-|=)?\s*(?:of\s+|in\s+)?(" + _A_DATE + r")"
    r"|(?:trained|training data|data)\s+(?:on\s+data\s+)?(?:up\s+to|until|through)\s+(" + _A_DATE + r")",
    re.I,
)


def normalised(text: Any) -> str:
    """A stated date as "YYYY-MM": "June 2024" and "2024-06" are "2024-06"; a year alone is its first month (a
    later month would flag fewer libraries as newer than the model); "" for no date."""
    words = str(text or "").strip().lower().replace(",", " ")
    found = re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?(?:t.*)?", words)
    if found and 1 <= int(found.group(2)) <= 12:
        return f"{found.group(1)}-{int(found.group(2)):02d}"
    found = re.fullmatch(r"([a-z]{3,9})\.?\s+(\d{4})", words)
    if found and found.group(1) in _MONTHS:
        return f"{found.group(2)}-{_MONTHS[found.group(1)]:02d}"
    found = re.fullmatch(r"(\d{4})", words)
    if found:
        return f"{found.group(1)}-01"
    return ""


def found_on_the_card(info: dict[str, Any] | None, readme: str = "") -> dict[str, dict[str, Any]]:
    """{FIELD: found} from a model card: its text's stated cutoff, else its repository's creation month as an upper
    bound; {} when neither says. Never raises."""
    try:
        for match in _STATED.finditer(str(readme or "")):
            month = normalised(match.group(1) or match.group(2))
            if month:
                return {FIELD: {"value": month, "source": "model card", "note": "stated in the card's text"}}
        created = normalised(str((info or {}).get("createdAt") or "")[:10])
        if created:
            return {FIELD: {"value": created, "source": "model card",
                            "note": "the month its repository was created: an upper bound, its data ends before"}}
    except Exception:  # noqa: BLE001 - unknown
        pass
    return {}


def of(model_name: str) -> str:
    """The training-data cutoff ("YYYY-MM") kept for `model_name`, the owner's over what was found; "" when unknown."""
    if not model_name:
        return ""
    try:
        from app.models.capabilities import value

        return normalised(value(model_name, FIELD))
    except Exception:  # noqa: BLE001 - unknown
        return ""


def _names(model: Any) -> list[str]:
    names = [str(getattr(model, attribute, "") or "") for attribute in ("model_name", "model")] if model else []
    try:
        from app.models.model_pin import pinned_snapshot

        pinned = pinned_snapshot()
        if pinned:
            names.append(str(pinned.get("MODEL_NAME") or ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.models.model_guidance import served_now

        names.append(served_now())
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.models import _runtime_settings

        names.append(str(_runtime_settings().model_name or ""))
    except Exception:  # noqa: BLE001
        pass
    return [name for name in dict.fromkeys(names) if name and isinstance(name, str)]


def of_the_build_model(model: Any = None) -> str:
    """The cutoff of the model that builds and fixes: `model`'s, else the run's pinned or served model's; "" when no
    name has one. Never raises."""
    for name in _names(model):
        found = of(name)
        if found:
            return found
    return ""


__all__ = ["FIELD", "found_on_the_card", "normalised", "of", "of_the_build_model"]
