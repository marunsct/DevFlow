"""`loop.sh corpus accept` copies the accepted corpus into the worker, so the next harvest does not undo it.

Measured on one run: sixteen contract samples were accepted for a new reading on the host only; `loop.sh score` then
harvested the worker's corpus over the host's, the old results came back, and the suite's replay failed again.
"""
from pathlib import Path

LOOP = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "loop.sh"


def test_accept_copies_into_the_worker_after_accepting_here():
    text = LOOP.read_text()
    branch = text[text.index("  accept) "):text.index(";;", text.index("  accept) "))]
    assert "replay(accept=True)" in branch
    assert "docker cp data/corpus/. langchain-worker-1:/app/data/corpus/" in branch
    assert branch.index("replay(accept=True)") < branch.index("docker cp")
