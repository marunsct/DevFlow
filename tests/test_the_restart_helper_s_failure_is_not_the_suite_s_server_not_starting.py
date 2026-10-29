"""A restart test's own service stopping is that test's failure, not "the product did not start for the suite".

Deep review, acceptance A7: the harness's restart helper threw "the service exited with code N", which matched the
pattern for the suite's server never starting; one blocking "does not start" defect replaced the real failure, every
later file was skipped, and the fixers aimed at start-up.
"""
from __future__ import annotations

from app.acceptance import suite
from app.stacks.packs import _service


def test_the_helper_s_words_are_not_a_start_failure():
    assert "stopped (code" in _service.SERVICE_HELPER
    message = "Error: the service this test started stopped (code 1) before it answered"
    assert not suite._NEVER_STARTED.search(message)


def test_the_suite_s_own_server_failing_still_is():
    assert suite._NEVER_STARTED.search("Error: Process from config.webServer was not able to start. Exit code: 1")
    assert suite._NEVER_STARTED.search("the service exited with code 1 before answering")
