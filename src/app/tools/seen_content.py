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


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()


def remember(relative_path: str, content: str) -> None:
    """Record that this stage has seen `content` at `relative_path`."""
    seen = store(_PURPOSE, _FALLBACK)
    seen[str(relative_path)] = _digest(content)
    while len(seen) > MAX_FILES_REMEMBERED:
        seen.pop(next(iter(seen)))


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


def forget_everything() -> None:
    """Drop the no-stage fallback. For tests, which must not leak into each other."""
    _FALLBACK.clear()


__all__ = [
    "MAX_FILES_REMEMBERED",
    "changed_since_seen",
    "forget_everything",
    "remember",
]
