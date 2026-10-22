"""Read a severity the model wrote, in the vocabulary the schema asks for.

Four schemas in this harness name severity, and no two of them agree:

    milestone_reviewer     blocking, major, minor, suggestion
    architecture_reviewer  blocking, major, minor, informational
    security_reviewer      critical, high, medium, low, info
    ReportedDefect         blocking, major, minor

Each set is reasonable on its own. Together they are a trap: one model plays
every role in a run, and the word that was required of it two stages ago is a
validation error now. `app.graph.workflow._GATING_SEVERITIES` already carries
the scar - it gates on `{"blocking", "major", "critical", "high"}`, a union of
two vocabularies, because by the time findings reach it they are in both.

Measured on one run's `defect_fix_2_0`. The Testing specialist wrote a
complete, correct defect report and typed `"severity": "High"`. `High` is not
in `Literal["blocking", "major", "minor"]`, so the whole answer was rejected,
so `settled_answer` could not recognise it as an answer, so the stage wrote it
again - five times, identically, until the repeat guard stopped the run. The
defect it was describing was real and well-written. The run died over one word.

Refusing an out-of-vocabulary severity has never once caught a model that did
not know how bad something was. It only throws away the sentence that says so.
So: rank every word anyone actually uses, and hand back whichever of the
schema's own words sits closest. The vocabularies stay different, because each
is meaningful in its own domain; only the translation is shared.

Ties go to the more severe word. Turning a `medium` into a `major` costs a
reviewer a second look; turning it into a `suggestion` loses it.
"""

from __future__ import annotations

import re
from typing import Any

#: Severity words to a rank, 0 worst. Everything here has been seen in the
#: wild: the four schema vocabularies, the CVSS bands security models are
#: trained on, and the P0-P3 and Sev0-Sev4 ladders that come with them.
_RANKS: dict[str, int] = {
    # 0 - stops the work
    "blocking": 0, "blocker": 0, "critical": 0, "crit": 0, "fatal": 0,
    "severe": 0, "showstopper": 0, "p0": 0, "sev0": 0, "sev1": 0, "s0": 0,
    "urgent": 0,
    # 1 - has to be fixed, does not stop the work
    "major": 1, "high": 1, "serious": 1, "important": 1, "significant": 1,
    "p1": 1, "sev2": 1, "s1": 1,
    # 2 - between the two, which only some vocabularies have a word for
    "medium": 2, "moderate": 2, "normal": 2, "average": 2, "p2": 2,
    "sev3": 2, "s2": 2,
    # 3 - worth fixing, not worth blocking on
    "minor": 3, "low": 3, "small": 3, "slight": 3, "p3": 3, "sev4": 3,
    "s3": 3,
    # 4 - not a defect, an observation
    "informational": 4, "information": 4, "info": 4, "suggestion": 4,
    "nit": 4, "nitpick": 4, "trivial": 4, "cosmetic": 4, "note": 4,
    "advisory": 4, "none": 4, "n/a": 4, "p4": 4,
}


#: `sev 1`, `p-0`, `s 2` - the same ladder with a separator in it.
_LADDER_GAP = re.compile(r"\b(sev|p|s)[\s\-_]+(\d)\b")


def rank_of(value: Any) -> int | None:
    """Where this word sits on the ladder, or None if it is not a severity."""
    word = str(value or "").strip().lower().strip(".:!-_ ")
    if not word:
        return None
    if word in _RANKS:
        return _RANKS[word]
    # "Sev 1", "P 0", "S-2": the ladder written with a space or a dash.
    word = _LADDER_GAP.sub(r"\1\2", word)
    if word in _RANKS:
        return _RANKS[word]
    # "High severity", "blocking issue" - the word is in there somewhere.
    for part in word.replace("-", " ").replace("/", " ").replace("_", " ").split():
        if part in _RANKS:
            return _RANKS[part]
    return None


def normalise(value: Any, allowed: tuple[str, ...]) -> Any:
    """`value` expressed in `allowed`, or `value` untouched if it cannot be.

    Untouched rather than guessed: a value this does not recognise is left for
    the schema to reject and for `settled_answer._why_it_was_not_accepted` to
    report, which tells the model the exact field and the exact choices. That
    is a better outcome than quietly recording a severity nobody wrote.
    """
    if not isinstance(value, str):
        return value
    word = value.strip().lower()
    if word in allowed:
        return word
    wanted = rank_of(value)
    if wanted is None:
        return value
    ranked = [(rank_of(name), name) for name in allowed]
    candidates = [(r, name) for r, name in ranked if r is not None]
    if not candidates:
        return value
    # Nearest rank; on a tie the more severe word, which is the lower rank.
    best = min(candidates, key=lambda pair: (abs(pair[0] - wanted), pair[0]))
    return best[1]


def validator_for(*allowed: str) -> Any:
    """A `mode="before"` validator that normalises onto `allowed`.

    Used as::

        _severity = field_validator("severity", mode="before")(
            validator_for("blocking", "major", "minor")
        )
    """

    def _normalise(cls: Any, value: Any) -> Any:
        return normalise(value, allowed)

    return classmethod(_normalise)


__all__ = ["normalise", "rank_of", "validator_for"]
