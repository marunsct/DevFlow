"""A product that failed to start is shown with the error it stated, not only the stack frames at the end of its output.

Measured on one Java run: the service exited at start with a long stack trace, and the 1,200 characters kept from the
end were frames and "... 44 common frames omitted"; the exception's message and its "Caused by:" line, naming the
setting the database refused, were cut, and two fix rounds passed without it.
"""
from __future__ import annotations

from app.acceptance import start_probe
from app.acceptance.what_went_wrong import shown

CAUSE = ('Caused by: org.h2.jdbc.JdbcSQLNonTransientConnectionException: Unsupported connection setting '
         '"DB_CLOSE_ON_EXIT_X" [90113-232]')
TRACE = "\n".join([
    "APPLICATION FAILED TO START",
    "org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'entityManagerFactory'",
    *[f"\tat org.hibernate.layer{n}.Thing.call(Thing.java:{n})" for n in range(40)],
    CAUSE,
    *[f"\tat org.h2.message.DbException.get(DbException.java:{n})" for n in range(40)],
    "\t... 44 common frames omitted",
])


def test_the_cause_reaches_the_fixer_within_the_limit():
    said = shown(TRACE, start_probe.MOST_OUTPUT)

    assert "Unsupported connection setting" in said
    assert "BeanCreationException" in said
    assert len(said) <= start_probe.MOST_OUTPUT + 200
    assert "DbException.java" not in said, "frames give way to what was stated"


def test_short_output_comes_back_as_it_was():
    assert shown("listening on 3000\nError: EADDRINUSE: address already in use", 1200).endswith("address already in use")


def test_the_container_probe_asks_for_more_than_it_shows():
    assert start_probe._what_the_sandbox_returns() > start_probe.MOST_OUTPUT  # noqa: SLF001
