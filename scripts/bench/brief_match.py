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
from pathlib import Path

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


def benchmark_of(text: str, benchmarks: str | Path) -> str:
    """The benchmark (with hidden tests) whose brief `text` is, or "" when none is.

    Measured on one run: `loop.sh score` took the benchmark from the brief last started on the host while the other
    port ran another family, and scored a product against hidden tests written for a different brief.
    """
    best, best_ratio = "", 0.0
    for brief in sorted(Path(benchmarks).glob("*/brief.md")):
        if not (brief.parent / "hidden").is_dir():
            continue
        ratio = similarity(text, brief.read_text(encoding="utf-8", errors="replace"))
        if ratio > best_ratio:
            best, best_ratio = brief.parent.name, ratio
    return best if best_ratio >= SAME_AT_LEAST else ""


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--benchmark-of":
    print(benchmark_of(sys.stdin.read(), sys.argv[2]))
elif __name__ == "__main__" and len(sys.argv) == 3:
    texts = [sys.stdin.read() if path == "-" else open(path, encoding="utf-8", errors="replace").read() for path in sys.argv[1:]]
    print(verdict(*texts))
