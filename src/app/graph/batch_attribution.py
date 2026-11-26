"""Which fixer of a broken batch broke it: only a fixer that changed something is a suspect (LF.1543).

A batch of fixes made side by side is measured once; when it breaks what passed before it, `engineering.after_a_batch`
puts back one fixer's files at a time to find whose change broke it, and reverts only that one (A3). It gave up, and
reverted the whole batch, as soon as one fixer of the batch had written no file. Measured on a web front-end run: of a
batch of two, one fixer's only edit was refused (the other fixer had changed the file since it read it) and its rewrite
found no file it might write, so it changed nothing; the other rewrote the page's component and broke a unit test. Both
were recorded "reverted: its batch broke 1 test", both were sent to be fixed alone, and the fixer that changed nothing
was told its change had broken a test.

Now a fixer that wrote nothing is not a suspect: the search runs over the fixers that wrote. When every product file the
batch changed was written by one fixer, that fixer is the culprit with no further measurement: putting its files back
leaves the workspace as it was measured before the batch. Otherwise each writer's files are put back in turn and the
rest measured, as before. Each broken batch leaves one transcript record of how it was settled, which
`scripts/loop/effects.py` counts as "batch reverts by cause".
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

#: The transcript record of one broken batch's settling.
RECORD_KIND = "batch_measured"
#: How a broken batch was settled.
ONLY_WRITER = "the one fixer that changed the product put back, no measurement needed"
ONE_CULPRIT = "one fixer's change put back, the rest measured sound and kept"
NO_ONE_CULPRIT = "no one fixer's change alone: the whole batch put back"
NOT_TOLD_APART = "no fixer's writes recorded: the whole batch put back"


def _plain(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def writers(fixers: Sequence[tuple[str, Sequence[str]]]) -> list[tuple[str, list[str]]]:
    """The fixers whose change can have broken their batch: those that wrote a file, in the order given."""
    return [(name, [str(path) for path in files]) for name, files in fixers if files]


def the_only_writer(fixers: Sequence[tuple[str, Sequence[str]]], changed: Sequence[str]) -> str:
    """The fixer that wrote every product file the batch changed, when one did and no other fixer wrote; "" otherwise.

    `changed` is every product path the batch changed, as git lists them. A change no fixer's writes name (a command
    that wrote a file) leaves the answer "": it may be any fixer's, and is measured.
    """
    who = writers(fixers)
    if len(who) != 1 or not changed:
        return ""
    name, files = who[0]
    return name if {_plain(path) for path in changed} <= {_plain(path) for path in files} else ""


def changed_between(root: str, older: str, newer: str) -> list[str] | None:
    """The product paths that differ between two commits, added, changed or removed; None when git cannot say."""
    from app import ci

    if not older or not newer:
        return None
    listed = ci._git(Path(root), "diff", "--name-only", "--no-renames", "--relative", older, newer, "--", ".",
                     *ci.NOT_THE_PRODUCT)
    if listed is None or listed.returncode != 0:
        return None
    return [line.strip() for line in listed.stdout.splitlines() if line.strip()]


def note(stage_name: str, how: str, batch: int, put_back: Sequence[str], broke: Sequence[str],
         cleared: Sequence[str] = ()) -> None:
    """Record how a broken batch was settled; `cleared` are its fixers that wrote nothing and were kept. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage_name, RECORD_KIND, how=how, batch=batch, put_back=list(put_back),
               broke=list(broke)[:3], cleared=list(cleared))
    except Exception:  # noqa: BLE001 - a record never changes how the batch is settled
        logger.debug("Could not record how a broken batch was settled", exc_info=True)


def effects_lines(records: list[dict]) -> list[str]:
    """LF.1543: the broken batches, by how each was settled, and the fixers that wrote nothing kept out of blame."""
    label = "LF.1543 batch reverts by cause"
    settled = [r for r in records if isinstance(r, dict) and r.get("kind") == RECORD_KIND]
    if not settled:
        return [f"     -  {label}: not reached"]
    by_how = Counter(str(r.get("how") or "?") for r in settled)
    fixers = sum(int(r.get("batch") or 0) for r in settled)
    put_back = sum(len(r.get("put_back") or []) for r in settled)
    cleared = sum(len(r.get("cleared") or []) for r in settled)
    return [f"  {len(settled):>4}  {label} (" + "; ".join(f"{how} {n}" for how, n in by_how.most_common())
            + f"); {put_back} of {fixers} fixers put back; {cleared} that wrote nothing kept out of blame"]


__all__ = ["NOT_TOLD_APART", "NO_ONE_CULPRIT", "ONE_CULPRIT", "ONLY_WRITER", "RECORD_KIND", "changed_between",
           "effects_lines", "note", "the_only_writer", "writers"]
