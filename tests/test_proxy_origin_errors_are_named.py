"""A proxy origin timeout is explained, not left as a bare status code.

Found on 2026-09-21 watching a live run stall on `specialist_ui_ux_2`::

    HTTP Request: POST https://...trycloudflare.com/v1/chat/completions
        "HTTP/1.1 524 <none>"
    Retrying request in 120.000000 seconds (retry 1 of 3)

Two timeouts are in play and only one is ours. `_request_timeout()` derived
433 seconds from the measured generation rate; the Cloudflare quick tunnel in
front of the model server caps an origin response at about 100 seconds and will
not be configured otherwise. The smaller wins, so the derived ceiling never
applies - and nothing in the log said so.

This is the codebase's own recurring lesson (`Say which fault the answer had,
not the nearest one`) applied to the transport: the retry behaviour is fine, the
silence about *why* is not.
"""

from __future__ import annotations

import logging

import pytest

from app.observability.proxy_timeouts import PROXY_ORIGIN_ERRORS, _ProxyErrorFilter


@pytest.fixture(autouse=True)
def _forget_rate_limit():
    """The observer stays quiet for 60s per code; tests need a clean slate."""
    from app.observability import proxy_timeouts

    proxy_timeouts._last_reported.clear()
    yield
    proxy_timeouts._last_reported.clear()


def _httpx_record(status: int) -> logging.LogRecord:
    """A record shaped like the one httpx actually emits."""
    return logging.LogRecord(
        name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
        msg='HTTP Request: POST https://example.trycloudflare.com/v1/chat/completions '
            '"HTTP/1.1 %d <none>"' % status,
        args=(), exc_info=None,
    )


class TestItNamesTheCause:
    def test_a_524_is_explained(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            _ProxyErrorFilter().filter(_httpx_record(524))
        assert "524" in caplog.text
        assert "proxy" in caplog.text.lower()
        assert "100 seconds" in caplog.text, "the actual cap should be named"

    def test_it_names_the_derived_timeout_that_is_being_overridden(self, caplog):
        """The mismatch is the finding; one number without the other is half of it."""
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            _ProxyErrorFilter().filter(_httpx_record(524))
        assert "request timeout this deployment derived" in caplog.text

    def test_it_says_what_to_change(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            _ProxyErrorFilter().filter(_httpx_record(524))
        assert "MODEL_MAX_OUTPUT_TOKENS" in caplog.text

    @pytest.mark.parametrize("code", sorted(PROXY_ORIGIN_ERRORS))
    def test_every_origin_error_code_is_explained(self, code, caplog):
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            _ProxyErrorFilter().filter(_httpx_record(code))
        assert str(code) in caplog.text


class TestItStaysOutOfTheWay:
    def test_a_healthy_response_says_nothing(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            _ProxyErrorFilter().filter(_httpx_record(200))
        assert caplog.text == ""

    def test_an_ordinary_error_is_not_claimed_as_a_proxy_fault(self, caplog):
        """A 500 from the model server itself is not a proxy origin error.

        Blaming the proxy for a fault that is not the proxy's would send an
        operator to fix the wrong thing.
        """
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            _ProxyErrorFilter().filter(_httpx_record(500))
        assert caplog.text == ""

    def test_it_never_suppresses_the_original_line(self):
        """It observes. A filter that returned False would eat httpx's own log."""
        assert _ProxyErrorFilter().filter(_httpx_record(524)) is True
        assert _ProxyErrorFilter().filter(_httpx_record(200)) is True

    def test_it_does_not_repeat_itself_on_every_retry(self, caplog):
        """Three retries of one stall is one cause, not three."""
        f = _ProxyErrorFilter()
        with caplog.at_level(logging.WARNING, logger="app.observability.proxy_timeouts"):
            f.filter(_httpx_record(524))
            f.filter(_httpx_record(524))
            f.filter(_httpx_record(524))
        assert caplog.text.count("MODEL_MAX_OUTPUT_TOKENS") == 1

    def test_a_malformed_record_cannot_break_logging(self):
        record = logging.LogRecord(
            name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
            msg="HTTP Request: nothing parseable here", args=(), exc_info=None,
        )
        assert _ProxyErrorFilter().filter(record) is True


class TestItIsActuallyInstalled:
    def test_the_worker_installs_it(self):
        import inspect

        from app.server import tasks

        assert "proxy_timeouts" in inspect.getsource(tasks._init_worker_process), (
            "the worker makes every model call; without this the diagnostic never fires"
        )

    def test_installing_twice_is_harmless(self):
        from app.observability.proxy_timeouts import install

        install()
        install()

    def test_it_attaches_to_handlers_not_only_the_logger(self):
        """A logger filter runs only where the record is created.

        Verified live on 2026-09-21: attached to the `httpx` logger alone, in
        the Celery pool child, two real `HTTP/1.1 524` responses went past
        without the diagnostic firing - Celery routes worker output through its
        own handlers. A handler filter sees a record wherever it came from.
        """
        import logging

        from app.observability.proxy_timeouts import _already_watching, install

        handler = logging.StreamHandler()
        logging.getLogger().addHandler(handler)
        try:
            install()
            # Asked of the handler, not of a set of remembered ids. See
            # `_already_watching`: an id set answers a different question and
            # gets it wrong as soon as an address is reused.
            assert _already_watching(handler)
        finally:
            logging.getLogger().removeHandler(handler)

    def test_a_later_call_picks_up_handlers_that_appeared_since(self):
        """Celery installs its handlers after `worker_process_init` fires.

        A single "already installed" flag meant the first call attached to the
        handlers that existed then - none - and every later call returned early.
        """
        import logging

        from app.observability.proxy_timeouts import _already_watching, install

        install()
        handler = logging.StreamHandler()
        logging.getLogger().addHandler(handler)
        try:
            assert not _already_watching(handler)
            install()
            assert _already_watching(handler)
        finally:
            logging.getLogger().removeHandler(handler)

    def test_a_reused_address_does_not_hide_a_live_handler(self):
        """The defect the full suite found in the first version of this.

        `install()` remembered `id(target)`. CPython hands a new object the
        address of one it has just freed, so a handler created after an earlier
        one was collected could be taken for already-attached and never get the
        filter. Simulated here by attaching, dropping the handler, and bringing
        a fresh one in: the new handler must be watched on its own account.
        """
        import logging

        from app.observability.proxy_timeouts import _already_watching, install

        root = logging.getLogger()
        first = logging.StreamHandler()
        root.addHandler(first)
        try:
            install()
            assert _already_watching(first)
        finally:
            root.removeHandler(first)
        del first

        second = logging.StreamHandler()
        root.addHandler(second)
        try:
            install()
            assert _already_watching(second), (
                "a new handler was skipped, so the 524 it carries goes unnamed"
            )
        finally:
            root.removeHandler(second)

    def test_attaching_twice_does_not_stack_filters(self):
        """Idempotence is the other half: one filter, however often installed."""
        import logging

        from app.observability.proxy_timeouts import _ProxyErrorFilter, install

        handler = logging.StreamHandler()
        logging.getLogger().addHandler(handler)
        try:
            install()
            install()
            install()
            mine = [f for f in handler.filters if isinstance(f, _ProxyErrorFilter)]
            assert len(mine) == 1, f"{len(mine)} copies of the observer"
        finally:
            logging.getLogger().removeHandler(handler)

    def test_the_worker_reinstalls_once_logging_is_up(self):
        import inspect

        from app.server import tasks

        assert "task_prerun" in inspect.getsource(tasks)
