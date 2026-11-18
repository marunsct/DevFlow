"""Of the versions of a file several passes wrote, the one the compiler reported fewest findings in.

Deep review 2026-11-18 (A2): the rewrite of a fix ran up to three whole-file passes and kept the last, even when it
ended "The compiler still reports ..." and an earlier pass had compiled; a draft's repair did the same in two passes
and never measured its last. The compiler's answer, not the order of the passes, decides what is kept. A tie goes to
the later pass: it was written with more of the compiler's words in front of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable


def findings_in(path: str, reported: Iterable[str]) -> int:
    """How many of `reported` (lines naming files as `` `path` ``) are about `path`."""
    return sum(1 for line in reported if f"`{path}`" in line)


class BestVersions:
    """Per file, the version with the fewest findings offered so far; a tie keeps the later."""

    def __init__(self) -> None:
        self._best: dict[str, tuple[int, str]] = {}

    def offer(self, path: str, content: str, findings: int) -> None:
        kept = self._best.get(path)
        if kept is None or findings <= kept[0]:
            self._best[path] = (findings, content)

    def offer_as_they_are(self, root: str | Path, paths: Iterable[str], reported: Iterable[str]) -> None:
        """Offer each of `paths` as it is on disk now, with its findings among `reported`."""
        reported = list(reported)
        for path in paths:
            try:
                content = (Path(root) / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.offer(path, content, findings_in(path, reported))

    def put_back(self, root: str | Path, write: Callable[[str, str, str], object]) -> list[str]:
        """Write back each file whose version on disk is not its best; the files put back. Never raises."""
        put_back = []
        for path, (_, content) in self._best.items():
            try:
                if (Path(root) / path).read_text(encoding="utf-8", errors="replace") == content:
                    continue
                write(str(root), path, content)
                put_back.append(path)
            except Exception:  # noqa: BLE001 - the file as it is stays
                continue
        return put_back
