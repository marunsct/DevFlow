"""The page a failed test met, as much of it as a result keeps: the part around what the test looked for (LF.1460).

The page a failing test met was kept as its first 900 characters, the same cut for every failure. Measured on 27
failing tests with a page: 12 were cut, and on one medium run two pages held the field their tests waited for past
the cut - "[AC-6] user login with valid credentials succeeds" waited for `getByLabel('Email')`, and `textbox "Email *"`
stood at character 990 of 1,303, after the site's navigation. The brief then showed a page without the field the test
could not fill, and the field read as absent.

`kept` keeps a page whole when it fits; otherwise the lines around the first line naming what the test looked for
(`failure_said.what_it_sought`), with the lines that hold them above it - the page's landmarks, by their indentation -
and says how many lines each cut left out. A page whose test sought nothing nameable, or nothing on the page, keeps its
head as before. `in_order` gives the room to the first failing test of each criterion before a second test of one.
Pure; never raises.
"""
from __future__ import annotations

from typing import Any, Iterable

#: Characters of one page a result keeps: more than the 900 it was, still bounded so a red suite's summary stays
#: readable (the largest real page measured was 5,015).
ROOM = 1_500


def _depth(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _cut(count: int) -> list[str]:
    return [f"... {count} more line(s)"] if count > 0 else []


def kept(page: str, sought: Iterable[str] = (), room: int = ROOM) -> str:
    """`page` cut to about `room` characters around the first line naming something in `sought`; its head when none."""
    page = str(page or "")
    if len(page) <= room:
        return page
    lines = page.splitlines()
    names = [str(name) for name in sought or () if str(name).strip()]
    # As written first, then in any case.
    hit = next((i for i, line in enumerate(lines) for name in names if name in line), None)
    if hit is None:
        hit = next((i for i, line in enumerate(lines) for name in names if name.lower() in line.lower()), None)
    if hit is None:
        head, used = [], 0
        for line in lines:
            if used + len(line) + 1 > room:
                break
            head.append(line)
            used += len(line) + 1
        return "\n".join(head + _cut(len(lines) - len(head)))
    # The lines that hold the hit, nearest first: each line above it with less indentation than the last one taken.
    above, depth = [], _depth(lines[hit])
    for index in range(hit - 1, -1, -1):
        if _depth(lines[index]) < depth:
            above.append(index)
            depth = _depth(lines[index])
    above.reverse()
    window = {hit}
    used = len(lines[hit]) + 1 + sum(len(lines[i]) + 1 for i in above)
    low, high = hit, hit
    while True:
        grown = False
        for index in (high + 1, low - 1):
            if not 0 <= index < len(lines):
                continue
            cost = 0 if index in above else len(lines[index]) + 1
            if used + cost > room:
                continue
            window.add(index)
            used += cost
            low, high = min(low, index), max(high, index)
            grown = True
        if not grown:
            break
    shown, last = [], -1
    for index in sorted(set(above) | window):
        shown += _cut(index - last - 1)
        shown.append(lines[index])
        last = index
    return "\n".join(shown + _cut(len(lines) - last - 1))


def in_order(tests: Iterable[Any], criteria_of: Any) -> list[int]:
    """The positions of failed `tests`, the first failing test of each criterion first, then the rest in order.

    `criteria_of(test)` names a test's criteria. Measured: 23 failing page tests carried no page, the room taken by the
    first eight failures - several of one criterion - while other criteria's first failures had none.
    """
    firsts, rest, seen = [], [], set()
    for position, test in enumerate(tests):
        own = [c for c in criteria_of(test) or () if c not in seen]
        if own:
            firsts.append(position)
            seen.update(criteria_of(test) or ())
        else:
            rest.append(position)
    return firsts + rest


__all__ = ["ROOM", "in_order", "kept"]
