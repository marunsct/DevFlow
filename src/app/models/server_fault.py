"""Whether a diagnosis request failed because of the server, not the model: such a try is "not measured" (DX.1).

Read from the kept diagnoses: one hosted model's 413 "request too large" made it "weak" (0.583) with a tail
reminder; one local diagnosis lost 2 of 3 tries of a check to a proxy's 30-second timeout; another lost 27 of 36 tries
to 503s ("server_draining") and dropped connections, and was scored 0.139. Each was kept as the model's failure,
and the tier, the guides and the support matrix followed from an outage. A try that ended in a 5xx, a 408, 413 or
429, a timeout or a dropped connection says nothing about the model, so it is left out of the check's tries.

A 400 or 422 stays a failed try: the server read the request and refused what the model or the request did (a tool
call it could not parse, a named tool choice it does not take), which is a finding.
"""
from __future__ import annotations

import re

#: Statuses that are the server's or a proxy's, not the model's: busy, gone, too large, too many.
_SERVER_STATUSES = frozenset({408, 413, 429})
_STATUS_IN_TEXT = re.compile(r"\bError code: (\d{3})\b")


def _status(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status, int):
        return status
    found = _STATUS_IN_TEXT.search(str(error))
    return int(found.group(1)) if found else None


def server_fault(error: BaseException) -> str:
    """Why `error` is the server's and not the model's, in a few words; "" when it is a finding about the model."""
    status = _status(error)
    if status is not None and (status >= 500 or status in _SERVER_STATUSES):
        return f"the server answered {status}"
    name = type(error).__name__.lower()
    if "timeout" in name:
        return "the request timed out"
    try:
        import openai

        if isinstance(error, openai.APIConnectionError):
            return "the connection was dropped"
    except ImportError:  # pragma: no cover - the client is always installed
        pass
    text = str(error).lower()
    if "connection error" in text or "timed out" in text or "connection reset" in text:
        return "the connection was dropped"
    return ""


__all__ = ["server_fault"]
