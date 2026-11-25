"""The project setup never forbids running the scripts the tests are run with (deep review 2026-11-25, item 7).

Measured in 80 fixer and tester messages over 7 runs: "Reproduction steps: Run `npm run test:acceptance` ..." beside
"Kept by the harness: ... and the manifest scripts `test`, `test:acceptance`, `start`. They are test setup ... do not
change them, test them, run them yourself or build on them". Running the scripts is allowed and is how the tests run;
only the setup files are not to be executed on their own. The pack record is a real full-stack run's.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.stacks import contract

CAPTURED = Path(__file__).parent / "captured" / "fullstack_node_stack_pack.json"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _the_setup_block(tmp_path: Path) -> str:
    (tmp_path / ".harness").mkdir()
    shutil.copy(CAPTURED, tmp_path / contract.CONTRACT_FILE)
    return contract.describe(tmp_path, with_reference_code=False)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.:])\s+(?=[A-Z-])", text) if s.strip()]


def test_no_prohibition_names_running_a_test_script(tmp_path):
    block = _the_setup_block(tmp_path)

    kept = block[block.index("- Kept by the harness"):]
    kept = kept[:kept.index("\n")]
    sentences = _sentences(kept)
    # A prohibition reaches the scripts when it names them, or says "them" right after the sentence that does.
    reaching = [later for earlier, later in zip(["", *sentences], sentences)
                if "test:acceptance" in later or "test:acceptance" in earlier]
    assert [s for s in reaching if re.search(r"\bdo not\b[^.]*\brun\b", s)] == []


def test_the_scripts_are_named_as_the_way_the_tests_run(tmp_path):
    block = _the_setup_block(tmp_path)

    kept = block[block.index("- Kept by the harness"):]
    kept = kept[:kept.index("\n")]
    assert "`npm run test:acceptance`" in kept and "`npm test`" in kept
    assert "do not change them" in kept
    assert not BANNED.search(kept)
