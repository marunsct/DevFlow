"""A command's output, captured up to a bound: its head and its tail, never the whole of it.

Found in review: the sandbox and the acceptance helpers read a command's
stdout and stderr whole into memory and only then cut them down to what a
model is shown. A product that prints without end - a test logging every
request, a server echoing megabyte bodies - grew the Celery pool process by
everything it printed. The rlimits the sandbox applies bound the command, not
the process reading it, so that growth was outside every limit and ended in
the worker being killed.

What is kept is what is read: the start says what ran and how it began, the
end says how it finished (a test runner's summary is its last line). The
middle is counted and left out, and a digest of the whole stream stands in
its place, so two outputs that differ only in the middle still compare
different.
"""

from __future__ import annotations

import hashlib
import subprocess
import threading
from collections import deque
from typing import IO, Any

#: The most of one stream kept in memory, in characters: half from its start, half from its end.
MOST_CAPTURED_CHARACTERS_PER_STREAM = 8 * 1024**2

#: How much one read takes at most. `readline()` with no bound reads a line
#: whole, and a stream with no newline is one line.
READ_PIECE_CHARACTERS = 64 * 1024


class HeadAndTail:
    """One stream's output, kept to `limit` characters: the first half and the last half."""

    def __init__(self, limit: int | None = None) -> None:
        limit = limit or MOST_CAPTURED_CHARACTERS_PER_STREAM
        self.limit = limit
        self._head_room = limit // 2
        self._tail_room = limit - self._head_room
        self._head: list[str] = []
        self._head_size = 0
        self._tail: deque[str] = deque()
        self._tail_size = 0
        self.left_out = 0
        self._digest = hashlib.sha256()
        self._lock = threading.Lock()

    def append(self, piece: str) -> None:
        if not piece:
            return
        with self._lock:
            self._digest.update(piece.encode("utf-8", "replace"))
            if self._head_size < self._head_room:
                taken = piece[: self._head_room - self._head_size]
                self._head.append(taken)
                self._head_size += len(taken)
                piece = piece[len(taken):]
                if not piece:
                    return
            self._tail.append(piece)
            self._tail_size += len(piece)
            while self._tail_size > self._tail_room:
                oldest = self._tail[0]
                over = self._tail_size - self._tail_room
                if len(oldest) <= over:
                    self._tail.popleft()
                    self._tail_size -= len(oldest)
                    self.left_out += len(oldest)
                else:
                    self._tail[0] = oldest[over:]
                    self._tail_size -= over
                    self.left_out += over

    def text(self) -> str:
        """What was kept; when anything was left out, a line between head and tail says how much."""
        with self._lock:
            head, tail = "".join(self._head), "".join(self._tail)
            if not self.left_out:
                return head + tail
            return (
                f"{head}\n[... {self.left_out} characters of output left out here; "
                f"the whole stream's sha256 is {self._digest.hexdigest()[:16]} ...]\n{tail}"
            )


def read_into(stream: IO[str], kept: HeadAndTail, *, on_read: Any = None) -> None:
    """Read `stream` to its end in bounded pieces into `kept`, then close it. Never raises."""
    try:
        for piece in iter(lambda: stream.readline(READ_PIECE_CHARACTERS), ""):
            kept.append(piece)
            if on_read is not None:
                on_read()
    except (OSError, ValueError):
        # Undecodable output, or a closed pipe: what is left is drained
        # unread, or the command blocks on a full pipe for ever.
        raw = getattr(stream, "buffer", None)
        try:
            while raw is not None and raw.read(READ_PIECE_CHARACTERS):
                pass
        except (OSError, ValueError):
            pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def run_bounded(argv: list[str], *, timeout: float | None = None, **popen_options: Any) -> "subprocess.CompletedProcess[str]":
    """`subprocess.run(argv, capture_output=True, text=True)`, keeping each stream to `HeadAndTail`'s bound.

    Raises `subprocess.TimeoutExpired`, with the output so far, when `timeout`
    passes; the process is killed first, as `subprocess.run` does.
    """
    popen_options.setdefault("text", True)
    popen_options.setdefault("errors", "replace")
    process = subprocess.Popen(  # noqa: S603 - argv list, no shell; the caller chose the command
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_options
    )
    kept = {"stdout": HeadAndTail(), "stderr": HeadAndTail()}
    readers = [
        threading.Thread(target=read_into, args=(stream, kept[name]), daemon=True)
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
    ]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=5)
        raise subprocess.TimeoutExpired(
            argv, timeout or 0, output=kept["stdout"].text(), stderr=kept["stderr"].text()
        ) from None
    for reader in readers:
        reader.join(timeout=5)
    return subprocess.CompletedProcess(argv, process.returncode, kept["stdout"].text(), kept["stderr"].text())


__all__ = ["HeadAndTail", "MOST_CAPTURED_CHARACTERS_PER_STREAM", "read_into", "run_bounded"]
