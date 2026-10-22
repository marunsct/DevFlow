"""A locked test that calls an address the suite never serves fails by its own code.

Measured on one gate run: an acceptance helper built
`new URL('/api/tasks', 'http://localhost')` instead of using the suite's
`baseURL`, and every test that listed the product's items failed on
`connect ECONNREFUSED ::1:80` - charged to the product, while a fixer looked
for a server that was never meant to answer there.
"""
from __future__ import annotations

import re

import pytest

from app.stacks.packs import _javascript, _python


def _broke_itself(patterns, message):
    return any(re.search(pattern, message, re.I | re.M) for pattern in patterns)


@pytest.mark.parametrize("message", [
    "Error: apiRequestContext.get: connect ECONNREFUSED ::1:80\nCall log:\n  - → GET http://localhost/api/tasks",
    "Error: apiRequestContext.post: connect ECONNREFUSED 127.0.0.1:80",
])
def test_node_s_message_is_the_test_s_own(message):
    assert _broke_itself(_javascript.TEST_BUGS, message)


def test_python_s_message_is_the_test_s_own():
    message = ("requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=80): Max retries "
               "exceeded with url: /api/tasks (Caused by NewConnectionError: [Errno 111] Connection refused)")
    assert _broke_itself(_python.TEST_BUGS, message)


def test_the_suite_s_own_server_refusing_is_the_product_s():
    """The product not listening on the suite's port is the product's to fix."""
    assert not _broke_itself(_javascript.TEST_BUGS, "Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:39811")
    assert not _broke_itself(_python.TEST_BUGS, "HTTPConnectionPool(host='127.0.0.1', port=39811): Max retries exceeded")
