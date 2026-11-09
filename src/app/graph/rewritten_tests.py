"""A locked test that cannot pass rewritten by one gathered call, not by an agent loop (plan item 10 part 2, behind `NAMED_TEST_REWRITE`).

Reopening a locked suite for the tests the harness's checks named (or the QA lead's dispute named) restarted QA's
agent loop on the whole suite: the author listing, reading and searching, writing, running, and a review after it.
Measured: 5-10 minutes and 1.4-2.2M tokens per repair after the lock, to change one or two tests whose fault the
checks had already named. The harness holds everything the repair needs, as the product-fix rewrite
(`app.graph.rewritten_fixes`) does for a product file: the test's own text, the runner's failure message, the checks'
finding, the criterion the test proves, the API reference, and the head of its file for the imports and fixtures.

So each named test is rewritten in one call that is given exactly that, and what comes back is placed by the test's
title in its file. The same call is shown the other tests that fail with the same message and told to repair those
that have the very same fault the same way (`REPAIR_RULE` asks it of QA): a locked test is sent back once for its
fault, not once for each test that has it. A repair is accepted only if it keeps the file's text before its first test,
its tests by title, and at least half the assertions of each test it changed (the checks that let a repair be locked
again without a second review, `suite.only_the_repaired_tests_changed`). A test that cannot be placed by its title,
a reply that does not answer, or a file the workspace refuses puts every file back as it was and the agent loop
takes the repair, as before. What was written then goes straight to the review.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.observability.direct_calls import config_for_this_run

logger = logging.getLogger(__name__)

#: `NAMED_TEST_REWRITE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Tests one reply may rewrite, those named and those sharing their fault.
MOST_TESTS = 6
#: Characters of a failure message shown, and of a file's head (its imports and fixtures).
MOST_FAILURE_CHARACTERS = 3_000
MOST_HEAD_CHARACTERS = 4_000

SYSTEM = (
    "You correct automated tests of a software product. You reply with the complete replacement of each test you "
    "change, each under its title, and nothing else."
)


class _NamedTestRewrite:
    """`NAMED_TEST_REWRITE` as the switch registry reads one: off in code and in compose until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A locked suite reopened for named tests has each named test rewritten by one call that is given "
                   "the test, its failure, the checks' finding and the criterion, with the tests that fail the same "
                   "way repaired in the same call, and then goes straight to the review; QA's agent loop takes it "
                   "only if a test cannot be placed. A repair after the lock took 5-10 minutes and 1.4-2.2M tokens.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("NAMED_TEST_REWRITE", _NamedTestRewrite.ON_BY_DEFAULT)


named_test_rewrite_switch = _NamedTestRewrite()


def enabled() -> bool:
    return named_test_rewrite_switch.enabled()


@dataclass(frozen=True)
class Placed:
    """A test found in the suite: its file, its title there, and the name the runner reports it under."""

    path: str
    title: str
    name: str


def _same(title: str, name: str) -> bool:
    return bool(title) and bool(name) and (title == name or title in name or name in title)


def _tests_in(text: str) -> tuple[str, dict[str, str]] | None:
    """(text before the first test, {title: block}) when the blocks put together are the file again; else None."""
    from app.acceptance import suite

    head, tests = suite._the_tests_of(text)
    if not tests or head + "".join(tests.values()) != text:
        return None
    return head, tests


def place(root: str | Path, name: str, files: dict[str, str] | None = None) -> Placed | None:
    """The one test of the suite that `name` names, or None when none or several do (titles that repeat, a runner's prefix)."""
    from app.acceptance import suite

    base = Path(root)
    found: list[Placed] = []
    for path in suite.suite_files(root):
        relative = path.relative_to(base).as_posix()
        text = (files or {}).get(relative)
        if text is None:
            text = path.read_text(encoding="utf-8", errors="replace")
        read = _tests_in(text)
        if read is not None:
            found.extend(Placed(relative, title, name) for title in read[1] if _same(title, name))
    return found[0] if len(found) == 1 else None


def _first_line(message: str) -> str:
    return next((line.strip() for line in str(message or "").splitlines() if line.strip()), "")


def _results(root: str | Path) -> list[dict[str, Any]]:
    """Every test of the last measurement: its name, outcome, message and the criterion it carries."""
    from app.acceptance import suite

    saved = suite.last_result(root) or {}
    tests: list[dict[str, Any]] = []
    for group in ("criteria", "change_requests"):
        for item_id, item in (saved.get(group) or {}).items():
            for test in item.get("tests") or []:
                tests.append({**test, "criterion": item_id, "text": item.get("text", "")})
    return tests


def request_for(root: str | Path, targets: list[tuple[Placed, str, str]], siblings: list[tuple[Placed, str]],
                files: dict[str, str], *, reference: str = "", reason: str = "") -> str:
    """What one call is asked: `targets` as (test, the checks' finding, its failure message), and the `siblings`."""
    from app.graph.acceptance_nodes import REPAIR_RULE

    def block_of(test: Placed) -> str:
        return (_tests_in(files[test.path]) or ("", {}))[1].get(test.title, "").rstrip() + "\n"

    paths = sorted({test.path for test, _, _ in targets} | {test.path for test, _ in siblings})
    heads = "\n\n".join(
        f"--- The start of `{path}`, before its first test ---\n{((_tests_in(files[path]) or ('', {}))[0])[:MOST_HEAD_CHARACTERS]}"
        for path in paths
    )
    asked = []
    for test, finding, message in targets:
        criteria = " ".join(f"{item['criterion']}: {item['text']}" for item in _results(root) if item["name"] == test.name)[:600]
        asked.append(
            f"### {test.title}\nFile: `{test.path}`\n"
            + (f"The criterion it proves: {criteria}\n" if criteria else "")
            + f"What the checks found: {finding}\n"
            + (f"What the runner printed when it failed:\n{message[:MOST_FAILURE_CHARACTERS]}\n" if message.strip() else "")
            + f"The test as it is now:\n```\n{block_of(test)}```"
        )
    same = [
        f"### {test.title}\nFile: `{test.path}`\nIts failure begins: {_first_line(message)[:300]}\n"
        f"The test as it is now:\n```\n{block_of(test)}```"
        for test, message in siblings
    ]
    return "\n\n".join(part for part in (
        "A locked acceptance test cannot pass whatever the product does, because of an error in its own code. "
        "Correct it. " + REPAIR_RULE,
        ("The QA lead's ruling on it: " + reason.strip()) if reason.strip() else "",
        "--- The tests to correct ---\n" + "\n\n".join(asked),
        ("--- Other tests that fail with the same message ---\nIf one of these has the very same fault in its own "
         "code - the same wrong step, written the same way - correct it in this reply too, in the same way. If it "
         "fails for the product's behaviour, leave it out.\n\n" + "\n\n".join(same)) if same else "",
        heads,
        reference.strip(),
        "Reply with one section for each test you change: a line `### ` and the test's title exactly as above, then "
        "the complete corrected test in one fenced code block, from its first line to its last line as shown "
        "(including whatever follows it in the block, unchanged). Keep the title, keep what the test checks, and "
        "change only the code that is wrong.",
    ) if part)


def _text_of(reply: Any) -> str:
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def blocks_in(reply: str) -> dict[str, str]:
    """{title: the code of its fenced block} for each `### title` section of a reply."""
    found: dict[str, str] = {}
    title, code, inside = None, [], False
    for line in str(reply or "").splitlines():
        if not inside:
            heading = re.match(r"^###\s+(.+?)\s*$", line)
            if heading:
                title = heading.group(1).strip().strip("`")
            elif title is not None and line.startswith("```"):
                inside, code = True, []
        elif line.startswith("```"):
            found[title] = "\n".join(code) + "\n"
            title, inside = None, False
        else:
            code.append(line)
    return found


def spliced(text: str, title: str, block: str) -> str | None:
    """`text` with the test `title` replaced by `block`, or None when the result would not still be this suite's file.

    The text before the first test, the tests by title and the assertions are held: a replacement that loses a
    check, renames a test or drops what surrounds the tests is not a repair of the one test.
    """
    from app.acceptance import suite

    read = _tests_in(text)
    if read is None or title not in read[1] or not block.strip():
        return None
    head, tests = read
    # The blank lines that separate it from the next test are the file's, not the reply's.
    block = block.rstrip() + tests[title][len(tests[title].rstrip()):]
    after = _tests_in(head + "".join(block if name == title else body for name, body in tests.items()))
    if after is None or after[0] != head or list(after[1]) != list(tests) or title not in after[1]:
        return None
    had, has = suite._assertions_in(tests[title]), suite._assertions_in(after[1][title])
    if has < 1 or has < had * suite.LEAST_ASSERTIONS_KEPT:
        return None
    return head + "".join(after[1].values())


def repair(
    root: str | Path, findings: list[str], model: Any, *, which_test: Callable[[str], str], reference: str = "",
    reason: str = "", write: Callable[[str, str, str], Any] | None = None,
) -> dict[str, Any] | None:
    """The suite's files changed by rewriting the tests `findings` name, or None to leave the repair to the agent loop.

    Every named test must be placed and answered for; one that is not puts every file back and returns None. The
    result is {"files": [...], "tests": [titles rewritten, named and shared-fault], "calls": n}.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.acceptance import suite

    base = Path(root)
    if not findings or len(findings) > MOST_TESTS:
        return None
    if model is None:
        try:
            from app.models import build_default_chat_model

            model = build_default_chat_model()
        except Exception:  # noqa: BLE001 - no model, the agent loop repairs
            return None
    if not hasattr(model, "invoke"):
        return None
    if write is None:
        from app.tools.repository import write_approved_artifact

        write = write_approved_artifact
    originals = {path.relative_to(base).as_posix(): path.read_text(encoding="utf-8", errors="replace")
                 for path in suite.suite_files(root)}
    files = dict(originals)
    results = _results(root)
    named = [(finding, which_test(finding)) for finding in findings]
    targets: list[tuple[str, Placed, str]] = []
    for finding, name in named:
        found = place(root, name, files)
        if found is None:
            logger.info("The test `%s` cannot be placed by its title; QA's agent loop repairs it", name[:80])
            return None
        if all(found.title != test.title for _, test, _ in targets):
            targets.append((finding, found, next((str(item.get("message") or "") for item in results
                                                 if item["name"] == found.name), "")))
    # One call for the tests that fail with the same message: the same fault is corrected the same way, once.
    groups: list[list[tuple[str, Placed, str]]] = []
    for target in targets:
        group = next((g for g in groups if _first_line(g[0][2]) and _first_line(g[0][2]) == _first_line(target[2])), None)
        (group.append(target) if group is not None else groups.append([target]))
    rewritten: list[str] = []
    calls = 0
    for group in groups:
        shared = _first_line(group[0][2])
        siblings: list[tuple[Placed, str]] = []
        for item in results:
            other = place(root, item["name"], files) if shared and item.get("outcome") == "failed" else None
            if (other is not None and _first_line(item.get("message")) == shared
                    and all(other.title != test.title for _, test, _ in targets)
                    and all(other.title != sibling.title for sibling, _ in siblings)
                    and len(siblings) < MOST_TESTS - len(group)):
                siblings.append((other, str(item.get("message") or "")))
        try:
            reply = model.invoke([
                SystemMessage(content=SYSTEM),
                HumanMessage(content=request_for(root, [(test, finding, message) for finding, test, message in group],
                                                 siblings, files, reference=reference, reason=reason)),
            ], **config_for_this_run("acceptance_author"))
        except Exception as error:  # noqa: BLE001 - the agent loop takes what this could not
            logger.info("The rewrite of `%s` failed: %s", group[0][1].title[:80], str(error)[:200])
            return None
        calls += 1
        answered = blocks_in(_text_of(reply))
        for place_of, required in [*((test, True) for _, test, _ in group), *((s, False) for s, _ in siblings)]:
            block = answered.get(place_of.title)
            now = spliced(files[place_of.path], place_of.title, block) if block else None
            if now is None:
                if required:
                    logger.info("The rewrite of `%s` did not give a test that keeps the file's shape", place_of.title[:80])
                    return None
                continue
            files[place_of.path] = now
            rewritten.append(place_of.title)
    changed = sorted(path for path, text in files.items() if text != originals[path])
    if not changed:
        return None
    # The suite is open for its repair; the author's own first step, taken here.
    suite.unlock(root)
    try:
        for path in changed:
            write(str(base), path, files[path])
    except Exception as refused:  # noqa: BLE001 - every file back as it was, then the agent loop
        logger.info("A rewritten test file was refused (%s); the agent loop repairs", str(refused)[:200])
        for path, text in originals.items():
            (base / path).write_text(text, encoding="utf-8")
        return None
    # A test repaired for sharing the fault is under repair too, so the checks lock the suite again without a second review.
    suite.repairing(root, rewritten)
    logger.info("Rewrote %d locked test(s) in %d call(s): %s", len(rewritten), calls, "; ".join(t[:60] for t in rewritten))
    return {"files": changed, "tests": rewritten, "calls": calls}


__all__ = ["MOST_TESTS", "ON_BY_DEFAULT", "Placed", "blocks_in", "enabled", "named_test_rewrite_switch", "place", "repair",
           "request_for", "spliced"]
