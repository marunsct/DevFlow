"""Whether two briefs are the same brief, ignoring how the text was saved (Initiative AN, W.1).

`loop.sh score` compared the run's brief with the benchmark's byte for byte, so
a trailing newline or a CRLF made a run "started from another brief" and left
it out of the false-acceptance count. Text is compared after whitespace and
line endings are normalised, and the similarity is reported, so a near-copy is
still the benchmark's own brief and a different brief is not.

    python brief_match.py <run brief> <benchmark brief>      ("-" reads standard input)
    -> "yes 0.998" or "no 0.412"
"""
from __future__ import annotations

import difflib
import sys

#: At or above this, the run was started from the benchmark's own brief.
SAME_AT_LEAST = 0.97


def normalised(text: str) -> str:
    return " ".join(str(text or "").replace("\r\n", "\n").replace("\r", "\n").split())


def similarity(a: str, b: str) -> float:
    one, two = normalised(a), normalised(b)
    if one == two:
        return 1.0
    return round(difflib.SequenceMatcher(None, one, two, autojunk=False).ratio(), 4)


def verdict(a: str, b: str) -> str:
    ratio = similarity(a, b)
    return f"{'yes' if ratio >= SAME_AT_LEAST else 'no'} {ratio:g}"


if __name__ == "__main__" and len(sys.argv) == 3:
    texts = [sys.stdin.read() if path == "-" else open(path, encoding="utf-8", errors="replace").read() for path in sys.argv[1:]]
    print(verdict(*texts))
