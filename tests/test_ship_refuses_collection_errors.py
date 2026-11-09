"""`loop.sh ship` counts collection errors as an unclean suite, and keeps a caller's own attribution line.

Measured: two Python suites added as fixtures were collected as tests and the run ended `3 failed, 14463 passed, ...,
24 errors`; the script read only the `FAILED` lines, committed and pushed.
"""
from pathlib import Path

SHIP = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "ship.sh").read_text()


def test_an_error_line_makes_the_suite_unclean():
    assert 'grep -E "^(FAILED|ERROR) " "$log"' in SHIP


def test_a_message_with_its_own_attribution_is_not_given_a_second():
    assert '*"Co-Authored-By:"*' in SHIP
