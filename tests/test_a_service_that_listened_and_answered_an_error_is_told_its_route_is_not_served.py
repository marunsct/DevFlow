"""A service that started, listened and answered the readiness request with an error status is told so.

Measured on a measured run: gunicorn listened, the suite's readiness request to
the health route answered 404 for thirty seconds, the suite said "did not
start", and four fixes in two sprint attempts rewrote start-up code and password
hashing - each reverted - while the routes were never registered. The 404 sat in
the output past the six cause lines the excerpt keeps.
"""
from __future__ import annotations

import re

from app.acceptance.suite import PRODUCT_DID_NOT_START, the_product_did_not_start

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

OUTPUT = """failed on setup with "Failed: The service did not start:
[2026-10-23 00:15:01 +0000] [2920] [INFO] Starting gunicorn 22.0.0
[2026-10-23 00:15:01 +0000] [2920] [INFO] Listening at: http://127.0.0.1:33947 (2920)
[2026-10-23 00:15:01 +0000] [2920] [INFO] Using worker: sync
[2026-10-23 00:15:31 +0000] [2923] [INFO] Worker exiting (pid: 2923)
[2026-10-23 00:15:31 +0000] [2920] [ERROR] Worker (pid:2923) was sent SIGTERM!
[2026-10-23 00:15:31 +0000] [2920] [ERROR] Worker failed to boot again
error: one
error: two
error: three
error: four
failed: five
failed: six
E   urllib.error.HTTPError: HTTP Error 404: NOT FOUND
acceptance/conftest.py:56: in start
""" + "\\n".join(f"frame {n}" for n in range(12))


def test_a_listening_service_answering_404_is_told_its_route_is_not_served_ahead_of_the_excerpt():
    problem = the_product_did_not_start(OUTPUT)

    assert problem.startswith(PRODUCT_DID_NOT_START)
    lead = problem[:1500]
    assert "answered 404" in lead and "the route that request asks for is not served" in lead
    assert "registered with the application" in lead
    assert not BANNED.search(lead)


def test_a_service_that_never_listened_keeps_the_old_wording():
    crashed = 'failed on setup with "Failed: The service did not start:\nTraceback ...\nImportError: no module named x\n'
    problem = the_product_did_not_start(crashed)
    assert problem and "the route that request asks for" not in problem
