"""Past the author's room, the acceptance suite is written a file at a time, not in one reply (PA.4, always on).

Measured (per-agent audit, 2026-11-25): on the medium brief the suite writer opened at 1.15-1.28 of its summary
trigger - 120,000-127,000 characters of memory (the specification alone 87,000), 26,000 of prompt and 24,000 of tool
descriptions - and was asked for every test file of the sprint in one conversation. It was summarised from its first
calls; one visit of 88 calls made no write in 43 minutes (234 reads of 21 files, 17 summaries), and a visit past 40
calls began again from an empty conversation and did the same. On the small briefs every opening was at most 0.70 of
the trigger, and the suite was written in 2-3 visits.

So when the suite's first writing (a whole suite, or one sprint's addition) is past the author's room - its request,
the memory it is shown, the writer's framing and the work its criteria take (`CHARACTERS_A_CRITERION` each) together
fill the summary trigger - it is written in parts, one criterion group each, each part its own conversation that
writes one new test file:

- a group is at most the model's measured batch size (`acceptance_batches.batch_size`), else `CRITERIA_A_PART`;
- each part's request holds its criteria, only the interface contract's lines that name them (and the lines that
  name no criterion), and the suite's shared files as they are now, whole (helpers, fixtures, configuration: the
  files it needs to use what the earlier parts wrote);
- `acceptance_nodes._written_in_batches` runs the parts: a part whose criteria are covered is not asked again, and a
  criterion left without a test is asked for once more, alone.

A suite that fits is written in one request, as before; a repair with the review's findings is one request, as before.
Nothing here names a language, a framework or a runner. Never raises.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: Criteria in one part when the model's measured tier gives no batch size.
CRITERIA_A_PART = 4
#: The suite writer's system prompt and tool descriptions, in characters, as measured on the medium brief (26,000 of
#: prompt and 24,000 of tool descriptions): what every call of the stage carries before its messages.
WRITER_FRAMING = 50_000
#: The conversation one criterion's tests take once the stage has opened, in characters: a test file's part written
#: (about 1,500 characters for two tests) and the run's output read back.
CHARACTERS_A_CRITERION = 3_000
#: Characters of one shared file shown whole in a part's request, and of all of them.
MOST_SHARED_FILE = 12_000
MOST_SHARED = 30_000
#: The transcript record of a suite written a file at a time, and what it says.
RECORD_KIND = "suite_by_file"
SAID = ("The suite and its work would fill {share:.2f} of its author's summary trigger, so its {criteria} criteria are "
        "written a file at a time, in {count} parts")
#: How the shared files' section opens.
SHARED_HEADING = "--- The suite's shared files, as they are now ---"


def past_the_room(root: str | Path, model: Any, opening: str, stage: str, criteria: int) -> float | None:
    """The share of the author's summary trigger its one conversation would fill - the whole suite's request, the
    memory it is shown, the writer's framing and `CHARACTERS_A_CRITERION` of work for each of `criteria` - when that
    reaches the whole trigger; None when the suite fits its room. Never raises: None."""
    try:
        from app.agents import opening_room, project_memory
        from app.agents.role_agent import a_chat_model

        memory = ""
        if project_memory.enabled():
            memory, _ = project_memory.as_the_stage_opens(root, a_chat_model(model) if model is not None else model,
                                                          opening, stage)
        share = opening_room.share_of_the_trigger(
            len(opening) + len(memory) + WRITER_FRAMING + max(0, int(criteria)) * CHARACTERS_A_CRITERION, model)
        return share if share >= 1.0 else None
    except Exception:  # noqa: BLE001 - a suite that cannot be measured is written as before
        logger.debug("Could not tell whether the suite fits its author's room", exc_info=True)
        return None


def parts(criteria: Sequence[Any], model: Any = None) -> list[list[Any]]:
    """The criteria in order, one group a part: the model's batch size, else `CRITERIA_A_PART`."""
    from app.graph import acceptance_batches

    size = acceptance_batches.batch_size(_name_of(model)) or CRITERIA_A_PART
    return acceptance_batches.groups(criteria, size)


def _name_of(model: Any) -> str:
    return str(getattr(model, "model_name", "") or getattr(model, "model", "") or "") if model is not None else ""


def contract_for(group: Sequence[Any], contract: Sequence[str]) -> list[str]:
    """The interface contract's lines a part's criteria use: those naming one of them, and those naming none."""
    from app.acceptance.junit import tags_in

    own = {str(getattr(criterion, "id", "")) for criterion in group}
    kept = []
    for line in contract or ():
        named = [tag for tag in tags_in(str(line)) if tag.startswith(("AC-", "CR-"))]
        if not named or own.intersection(named):
            kept.append(line)
    return kept


def shared_files(root: str | Path) -> list[tuple[str, str]]:
    """The suite's files that declare no test - helpers, fixtures, configuration - with their text, in name order."""
    try:
        from app.acceptance import suite

        workspace = Path(root)
        with_tests = {name for name, _ in suite.declared_tests(root)}
        found: list[tuple[str, str]] = []
        for path in suite.suite_files(root):
            shown = path.relative_to(workspace).as_posix()
            if shown in with_tests:
                continue
            try:
                found.append((shown, path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
        return sorted(found)
    except Exception:  # noqa: BLE001 - no shared file shown
        return []


def note(index: int, total: int, group: Sequence[Any], files: Sequence[str], root: str | Path) -> str:
    """What a part is told: which part it is, that it writes one new file, and the shared files it uses, whole."""
    ids = ", ".join(str(getattr(c, "id", "")) for c in group)
    if index == 0:
        head = (
            f"--- This suite is written a file at a time, in {total} parts ---\n"
            f"You write part 1 of {total}: the criteria above, {ids}, in one new test file of their own. Put what the "
            "later parts will share - how the product is started, helpers, fixtures - in the suite's shared files "
            "(the runner's configuration or a helper module), not in your test file, so each later part can use it. "
            "The other criteria are written by the later parts; leave them to those.\n\n"
        )
    else:
        written = ", ".join(f"`{name}`" for name in files) or "the suite's files"
        head = (
            f"--- This suite is written a file at a time, in {total} parts ---\n"
            f"You write part {index + 1} of {total}: the criteria above, {ids}, in one new test file of their own, "
            f"named as the earlier ones are. Earlier parts wrote {written}; do not change or remove their tests. Use the "
            "shared files below as they are, and change one only to add what your tests need. Each test name carries "
            "the id of the criterion it proves. The other criteria are written by the other parts.\n\n"
        )
    return head + _shared_section(root)


def _shared_section(root: str | Path) -> str:
    shown, used = [], 0
    for name, text in shared_files(root):
        body = text if len(text) <= MOST_SHARED_FILE else text[:MOST_SHARED_FILE] + "\n... (cut here)"
        if used + len(body) > MOST_SHARED:
            shown.append(f"`{name}`: not shown here, read it before you use it.")
            continue
        used += len(body)
        shown.append(f"`{name}`:\n```\n{body.rstrip()}\n```")
    if not shown:
        return ""
    return f"{SHARED_HEADING}\n" + "\n".join(shown) + "\n\n"


def record(stage: str, share: float, criteria: int, count: int) -> None:
    """One transcript record of a suite written a file at a time (`loop.sh effects`). Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record as record_in

        record_in(_run_id_from_config(), stage, RECORD_KIND, message=SAID.format(share=share, criteria=criteria,
                                                                                 count=count),
                  criteria=criteria, parts=count, share=round(share, 2))
    except Exception:  # noqa: BLE001 - a record never fails the stage
        logger.debug("Could not record a suite written a file at a time", exc_info=True)


def effects_lines(records: Any) -> list[str]:
    """`loop.sh effects` (PA.4): suites written a file at a time, and the parts they were written in."""
    seen = [r for r in records or () if isinstance(r, dict) and r.get("kind") == RECORD_KIND]
    head = "PA.4 suites past the author's room written a file at a time"
    if not seen:
        return [f"     -  {head}: not reached"]
    parts_made = sum(int(r.get("parts") or 0) for r in seen)
    return [f"  {len(seen):>4}  {head} ({parts_made} parts)"]


__all__ = ["CHARACTERS_A_CRITERION", "CRITERIA_A_PART", "RECORD_KIND", "SAID", "SHARED_HEADING", "WRITER_FRAMING", "contract_for", "effects_lines", "note", "parts",
           "past_the_room", "record", "shared_files"]
