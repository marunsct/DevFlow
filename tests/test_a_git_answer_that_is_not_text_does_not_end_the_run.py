"""A run ended because `git diff` printed a byte that is not UTF-8.

A product file held a byte outside UTF-8; the measure that fingerprints the product read
`git diff` with strict decoding, the decode error is a ValueError (not an OSError or a
SubprocessError, which the call sites catch), and the run failed with its sprint half
fixed. Git output is read for its shape, never for exact text: it is decoded with
replacement everywhere it is read.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from app.acceptance import unstable
from app.agents import interface_changes
from app.graph import engineering

SRC = Path(__file__).resolve().parent.parent / "src" / "app"


def _repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "data.py").write_bytes(b"x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    (tmp_path / "data.py").write_bytes(b"x = 1\n# caf\xa7 \xff\n")
    return tmp_path


def test_the_product_is_fingerprinted_when_a_changed_file_holds_a_byte_that_is_not_text(tmp_path):
    root = _repo(tmp_path)
    assert unstable.fingerprint(root) != ""


def test_the_lines_a_fix_added_are_found_when_the_diff_holds_such_a_byte(tmp_path):
    root = _repo(tmp_path)
    assert engineering._lines_added(str(root), "HEAD", "data.py") == {2}


def test_the_last_commit_of_a_file_is_read_when_it_holds_such_a_byte(tmp_path):
    root = _repo(tmp_path)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "bytes"],
                   check=True, capture_output=True)
    assert "caf" in interface_changes._before(root, "data.py")


def test_no_git_call_in_the_product_decodes_strictly():
    strict = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        for node in ast.walk(ast.parse(text)):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "run"
                    and getattr(getattr(node.func, "value", None), "id", "") == "subprocess"):
                continue
            words = {k.arg for k in node.keywords}
            if ("text" in words or "universal_newlines" in words) and "errors" not in words \
                    and ('"git"' in (ast.get_source_segment(text, node) or "")):
                strict.append(f"{path.relative_to(SRC)}:{node.lineno}")
    assert not strict, strict
