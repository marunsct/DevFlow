"""What each stage last saw of a file, so a stale edit can say so.

`edit_artifact` takes a `find` passage the model copied from a read. When the
file changes between that read and the edit, `find` no longer matches and the
tool answers "Could not find that text", optionally with a diff of the lines
that differ. The model is then left to work out *why* its own copy is wrong.

It usually cannot, because the change was not its doing. Measured on run
8d28ee3f, `specialist_ui_ux_0`: the stage wrote `package.json`, ran
`npm install --save-dev jest-environment-jsdom`, and then tried to edit the
file using the text it had written. npm had reformatted the manifest and added
a dependency, so the diff it got back read:

    you sent:  "main": "app.js",
    file has:    "main": "app.js",   (line 5)
    you sent:      "jest": "^29.5.0"
    file has:      "jest": "^29.5.0",   (line 10)
    you sent:    }
    file has:      "jest-environment-jsdom": "^30.5.1"   (line 11)

Every line of which is accurate, and none of which says the one useful thing:
read the file again, it is not what you wrote. The stage abandoned the edit.

Installers are the common cause - `npm install` rewrites `package.json` and
`package-lock.json` on almost every run - but formatters, generators and any
command with a `--write` flag do the same, so this records the fact rather
than guessing the culprit.

Keyed per stage through `app.agents.stage_memory`, for the reason that module
documents: middleware and tool backends are rebuilt on every approval resume,
and a stage that writes a file between two reads is a stage that works.
"""

from __future__ import annotations

import hashlib

from app.agents.stage_memory import store

#: Files remembered per stage before the oldest is dropped. A stage touches a
#: handful; this is a ceiling against a pathological stage, not a working limit.
MAX_FILES_REMEMBERED = 128

_PURPOSE = "content last seen by this stage"
_HISTORY = "every state this stage has left a file in"

#: States remembered per file before the oldest is dropped. An oscillation
#: shows up within two or three, so this is a ceiling, not a working limit.
MAX_STATES_PER_FILE = 12


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()


def remember(relative_path: str, content: str) -> None:
    """Record that this stage has seen `content` at `relative_path`."""
    seen = store(_PURPOSE, _FALLBACK)
    seen[str(relative_path)] = _digest(content)
    while len(seen) > MAX_FILES_REMEMBERED:
        seen.pop(next(iter(seen)))


def record_state(relative_path: str, content: str) -> None:
    """Remember that this stage has left `relative_path` holding `content`."""
    history = store(_HISTORY, _FALLBACK_HISTORY)
    states = history.setdefault(str(relative_path), [])
    digest = _digest(content)
    if digest in states:
        states.remove(digest)
    states.append(digest)
    del states[:-MAX_STATES_PER_FILE]


def returned_to_an_earlier_state(relative_path: str, content: str) -> bool:
    """True when this stage has put the file back into a state it already had.

    An edit that undoes an earlier edit is not caught by anything else here.
    The repeat guard wants byte-identical consecutive calls; the no-op refusal
    wants `replace` to equal what it replaces; both see a *successful* edit
    with new arguments and let it through. The file oscillates and the stage
    spends its budget.

    Measured on run 8d28ee3f, `defect_fix_1_0`, which made 67 tool calls
    against a 40-call budget - 23 edits and 16 reads of one file. Its edits to
    `app.js` ran: `console.log(...)` -> `global.console.log(...)` ->
    `console.log(...)` -> `console.log(...)`, each reported "edited", toggling
    one line while the run paid for every turn.

    The most recent state is excluded: writing a file the content it already
    has is a no-op, which `_write_unless_it_changes_nothing` answers better.
    """
    history = store(_HISTORY, _FALLBACK_HISTORY)
    states = history.get(str(relative_path)) or []
    return _digest(content) in states[:-1]


_REPLACEMENTS = "passages this stage has already replaced"

#: Replacements remembered per file. A stage makes a few dozen edits at most.
MAX_REPLACEMENTS_PER_FILE = 64


def record_replacement(relative_path: str, find: str, replace: str) -> None:
    """Remember that this stage replaced `find` with `replace` in this file."""
    if not find:
        return
    applied = store(_REPLACEMENTS, _FALLBACK_REPLACEMENTS)
    pairs = applied.setdefault(str(relative_path), [])
    pairs.append((find, replace))
    del pairs[:-MAX_REPLACEMENTS_PER_FILE]


def what_replaced_it(relative_path: str, find: str) -> str | None:
    """What this stage put in place of `find` here, or None if it never did.

    An edit that misses because the stage already made it is not the same
    mistake as one that misses because the text was wrong, and the diff it
    would otherwise get compares its `find` against the replacement it wrote
    itself.

    `_already_applied` in `repository` catches the narrower case where the
    whole edit is re-sent - same `find`, same `replace`. Measured on run
    f81808a4, `specialist_testing_3` sent one `find` six times with the
    replacement varying each time, so that check stayed silent and the stage
    was answered with a character diff six times over.
    """
    applied = store(_REPLACEMENTS, _FALLBACK_REPLACEMENTS)
    for previous, replacement in reversed(applied.get(str(relative_path)) or []):
        if previous == find:
            return replacement
    return None


def changed_since_seen(relative_path: str, content: str) -> bool:
    """True when this stage has seen the file and it no longer matches.

    False when the stage has never read or written it: an edit whose `find` was
    never copied from a read is a different mistake, already answered by the
    messages about copying the passage exactly.
    """
    seen = store(_PURPOSE, _FALLBACK)
    previous = seen.get(str(relative_path))
    return previous is not None and previous != _digest(content)


#: Used when there is no stage to key on - outside a graph run, and in tests
#: that do not set one up. Shared deliberately: the alternative is a fresh dict
#: per call, which remembers nothing and makes `changed_since_seen` always
#: False, hiding a broken wiring behind a plausible answer.
_FALLBACK: dict[str, str] = {}


#: The history's counterpart to `_FALLBACK`, shared for the same reason.
_FALLBACK_HISTORY: dict[str, list[str]] = {}

#: And the replacement log's.
_FALLBACK_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {}


def forget_everything() -> None:
    """Drop the no-stage fallbacks. For tests, which must not leak into each other."""
    _FALLBACK.clear()
    _FALLBACK_HISTORY.clear()
    _FALLBACK_REPLACEMENTS.clear()


__all__ = [
    "MAX_FILES_REMEMBERED",
    "MAX_STATES_PER_FILE",
    "changed_since_seen",
    "forget_everything",
    "MAX_REPLACEMENTS_PER_FILE",
    "record_replacement",
    "record_state",
    "remember",
    "what_replaced_it",
    "returned_to_an_earlier_state",
]
