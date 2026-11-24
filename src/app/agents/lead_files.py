"""The files the technical lead reads to plan a sprint, ranked for its memory (LF.1286).

Measured on one medium run: a later sprint's technical lead made 243 reads of 20 files over 159 model calls with 21
summaries - the product's `models.py` and `main.py` 27 times each, the sprint's locked acceptance tests 13-18 times
each. Its memory held the plans and four trivial files; every file it read was "Not included here", so each read went
into the conversation, a summary dropped it, and the lead read it again. The same loop the reviews had (LF.1284).

So the lead is handed what it reads the way a review is: `for_the_plan` names the product's code, its configuration
and the locked acceptance tests due in the sprint being planned, and `review_files.held_for_review` holds them first
in the memory, numbered, behind the same size gate - a product whose files today's request and memory already show is
planned exactly as before. Which file comes first matters only past the memory's room: the sprint's own tests and
the code its criteria touch, taken in turn, then the configuration, then the tests of earlier sprints' criteria.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

#: The words of a criterion that can name what a file holds (as the memory's map reads words).
_WORD = re.compile(r"[a-z][a-z0-9_]{3,}")


def _the_suite_s_files(repo_root: Path, own: set[str], due: set[str]) -> tuple[list[str], list[str]]:
    """(the locked test files carrying a criterion of this sprint, most of its tests first; those carrying only an
    earlier sprint's due criteria), workspace-relative."""
    from collections import Counter

    from app.acceptance import junit, suite

    if not suite.is_locked(repo_root):
        return [], []
    mine: Counter = Counter()
    earlier: set[str] = set()
    for file, name in suite.declared_tests(repo_root):
        tags = set(junit.tags_in(name))
        if tags & own:
            mine[file] += 1
        elif tags & due:
            earlier.add(file)
    first = sorted(mine, key=lambda path: (-mine[path], path))
    return first, sorted(earlier - set(first))


def _in_turn(first: Sequence[str], second: Sequence[str]) -> list[str]:
    taken: list[str] = []
    for index in range(max(len(first), len(second))):
        taken.extend(group[index] for group in (first, second) if index < len(group))
    return taken


def for_the_plan(repo_root: str | Path, own: Iterable[str], due: Iterable[str],
                 criteria_texts: Iterable[str]) -> list[tuple[str, str]]:
    """The files a lead planning this sprint reads, each with its text, in the order its memory holds them.

    `own` are the ids of the criteria this sprint delivers, `due` every id due by its end (earlier sprints' too), and
    `criteria_texts` the text of this sprint's criteria. Product unit tests, documents, generated folders and the
    harness's kept files are not among them (`review_files.under_review`). Never raises: []."""
    try:
        from app.agents import project_memory
        from app.agents.review_files import under_review
        from app.analysis.file_kinds import classify_file

        root = Path(repo_root)
        own_ids, due_ids = {str(i) for i in own or ()}, {str(i) for i in due or ()}
        own_tests, earlier_tests = _the_suite_s_files(root, own_ids or due_ids, due_ids)
        suite_files = set(own_tests) | set(earlier_tests)
        product = [path for path in project_memory.current(root) if not path.startswith(("docs/", "."))]
        chosen = dict(under_review(root, [*own_tests, *sorted(product), *earlier_tests]))
        kind = {path: classify_file(path) for path in chosen}
        words = set(_WORD.findall(" ".join(str(t) for t in criteria_texts or ()).lower()))
        importance = project_memory.importance_of(root)

        def touched(path: str) -> tuple[int, int, str]:
            text = chosen[path].lower()
            return (-sum(1 for word in words if word in text), -importance.get(path, 0), path)

        code = sorted((p for p in chosen if p not in suite_files and kind[p] not in ("test", "config")), key=touched)
        config = [p for p in chosen if p not in suite_files and kind[p] == "config"]
        order = [*_in_turn([p for p in own_tests if p in chosen], code), *config,
                 *(p for p in earlier_tests if p in chosen)]
        return [(path, chosen[path]) for path in order]
    except Exception:  # noqa: BLE001 - the lead's memory as today
        logger.debug("Could not rank the files a lead reads", exc_info=True)
        return []


__all__ = ["for_the_plan"]
