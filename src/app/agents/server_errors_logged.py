"""Code that answers a server error logs the exception first (plan FX.1, LF.1410).

Measured on a medium run: every handler of the sign-up routes caught its exceptions and answered 500 without a log
line, so the server's log held only access lines. Two fixers spent 46 minutes on the criterion without seeing the
exception, and no lookup had an error to search. The fix stage asks for the log line when it meets this
(`app.graph.first_failure`); the builders of server code are told the rule before they write the handler.
"""

from __future__ import annotations

A_SERVER_ERROR_IS_LOGGED = (
    "Where the product catches an exception and answers with a server error, it logs that exception with its full "
    "trace first, in its own logging: an error answered without a log line leaves no one able to see its cause."
)

__all__ = ["A_SERVER_ERROR_IS_LOGGED"]
