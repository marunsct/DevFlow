"""A run's diagnostic bundle: what someone helping with a run needs, with no secret in it (deep review 2026-11-18, F1).

Asked for by the owner of a run from its page, never sent anywhere: the run's transcript as text, the run doctor's
account of it (`run_doctor`), and the run's record - only its named, non-secret fields. Every text in it passes
`scrubbed`: the value of any environment variable whose name says it is a secret (key, token, password, secret,
credential) is replaced wherever it appears, and so is anything shaped like an API key, a bearer token or a signed
token. No environment is included.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from typing import Any

#: The run record's fields the bundle carries; everything else (overrides, paths, payloads) stays out.
RECORD_FIELDS = (
    "run_id", "status", "current_stage", "stage_meaning", "created_at", "updated_at", "error", "delivery_mode",
    "local_only", "auto_approve", "approval_timeout_minutes", "review_policy", "completion_gaps", "document_names",
)
#: Environment variable names whose values are secrets.
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE", re.IGNORECASE)
#: Text shaped like a credential, whatever produced it.
_SECRET_SHAPE = re.compile(
    r"sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
    r"|(?<=://)[^/\s:@]+:[^/\s@]+(?=@)")
#: Shorter values are not looked for: a secret is never this short, and a common word would be.
_SHORTEST_SECRET = 8
REDACTED = "[redacted]"


def _secret_values(environment: dict[str, str] | None = None) -> list[str]:
    values = {value for name, value in (environment if environment is not None else os.environ).items()
              if _SECRET_NAME.search(name) and value and len(value) >= _SHORTEST_SECRET}
    return sorted(values, key=len, reverse=True)


def scrubbed(text: str, environment: dict[str, str] | None = None) -> str:
    """`text` with every secret value of the environment and every credential-shaped string replaced."""
    for value in _secret_values(environment):
        text = text.replace(value, REDACTED)
    return _SECRET_SHAPE.sub(REDACTED, text)


def the_record(record: Any) -> dict[str, Any]:
    """The run record's named, non-secret fields."""
    return {name: getattr(record, name, None) for name in RECORD_FIELDS}


def build(run_id: str, transcript: str, doctor: dict[str, Any], record: dict[str, Any],
          environment: dict[str, str] | None = None) -> bytes:
    """The bundle as a zip archive under a folder named for the run."""
    def clean(text: str) -> str:
        return scrubbed(text, environment)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{run_id}/README.txt", (
            "A run's diagnostic bundle: transcript.txt is every model call, reply, tool call and result; doctor.json "
            "the run doctor's account and suggested actions; run.json the run's record. Secrets and credential-shaped "
            "text are replaced with [redacted]; no environment is included.\n"))
        archive.writestr(f"{run_id}/transcript.txt", clean(transcript))
        archive.writestr(f"{run_id}/doctor.json", clean(json.dumps(doctor, indent=2, default=str)))
        archive.writestr(f"{run_id}/run.json", clean(json.dumps(record, indent=2, default=str)))
    return buffer.getvalue()


__all__ = ["RECORD_FIELDS", "REDACTED", "build", "scrubbed", "the_record"]
