"""A run that stopped moving, or a gate left waiting on a person, is told to a webhook and an email (plan OP.2).

Gates and stalls reached the browser only: a run that sat at a stage for an
hour, or a review nobody opened, was found when someone next looked. The API
process sweeps once a minute (beside `approval_timeouts`); each finding is sent
once - a marker under `DATA_DIR` keeps the several server processes from each
sending it - to `NOTIFY_WEBHOOK_URL` as JSON, and to `NOTIFY_EMAIL` when an SMTP
host is set. Nothing is sent when neither is set.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

#: Minutes a running run may go without a model or tool record before it is called stalled.
STALL_MINUTES = 20
#: Minutes a gate may wait on a person before it is told.
GATE_MINUTES = 30
_WAITING = {"waiting_for_approval": "approval", "waiting_for_review": "review"}


def _minutes(env: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(env) or default))
    except ValueError:
        return default


def _when(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def last_activity(run_id: str) -> datetime | None:
    """When the run's transcript was last written: its last model or tool record. None when it has none."""
    try:
        from app.observability.transcript import transcript_path

        path = transcript_path(run_id)
        if path is None or not path.exists():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:  # noqa: BLE001 - nothing known is nothing told
        return None


def findings(records: Iterable[Any], now: datetime,
             activity: Callable[[str], datetime | None] = last_activity) -> list[dict[str, Any]]:
    """Each run stalled or gate waited too long: run, kind, minutes and since when."""
    stall, gate = _minutes("STALL_MINUTES", STALL_MINUTES), _minutes("GATE_NOTICE_MINUTES", GATE_MINUTES)
    found = []
    for record in records:
        status = str(getattr(record, "status", "") or "")
        if status == "running":
            since = activity(record.run_id)
            if since is not None and (now - since).total_seconds() >= stall * 60:
                found.append({"run_id": record.run_id, "kind": "stalled", "stage": getattr(record, "current_stage", ""),
                              "minutes": int((now - since).total_seconds() // 60), "since": since.isoformat()})
        elif status in _WAITING:
            since = _when(getattr(record, "updated_at", None))
            if since is not None and (now - since).total_seconds() >= gate * 60:
                found.append({"run_id": record.run_id, "kind": f"{_WAITING[status]} waiting",
                              "stage": getattr(record, "current_stage", ""),
                              "minutes": int((now - since).total_seconds() // 60), "since": since.isoformat()})
    return found


def _already_told(finding: dict[str, Any]) -> bool:
    """Whether this finding, for this episode, was sent before; marks it sent when not."""
    folder = Path(os.environ.get("DATA_DIR") or "data") / "loop" / "notified"
    name = f"{finding['run_id']}-{finding['kind'].replace(' ', '_')}-{finding['since'].replace(':', '')}"
    marker = folder / name
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with open(marker, "x", encoding="utf-8"):
            pass
    except FileExistsError:
        return True
    except OSError:
        return False
    return False


def _text(finding: dict[str, Any]) -> str:
    if finding["kind"] == "stalled":
        return (f"Run {finding['run_id']} has had no model or tool activity for {finding['minutes']} minutes "
                f"(stage {finding['stage'] or '?'}).")
    return (f"Run {finding['run_id']}: a {finding['kind'].split()[0]} has waited {finding['minutes']} minutes "
            f"for a person (stage {finding['stage'] or '?'}).")


def send_webhook(url: str, finding: dict[str, Any]) -> None:
    body = json.dumps({**finding, "text": _text(finding)}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=5):
        pass


def send_email(to: str, finding: dict[str, Any]) -> None:
    host = os.environ.get("SMTP_HOST") or ""
    if not host:
        return
    message = EmailMessage()
    message["Subject"] = f"DevFlow: {finding['kind']} - {finding['run_id']}"
    message["From"] = os.environ.get("SMTP_FROM") or to
    message["To"] = to
    message.set_content(_text(finding))
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT") or 587), timeout=10) as smtp:
        if os.environ.get("SMTP_USER"):
            smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD") or "")
        smtp.send_message(message)


def notify(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Send each finding not sent before; the ones sent. Never raises."""
    webhook, email = os.environ.get("NOTIFY_WEBHOOK_URL") or "", os.environ.get("NOTIFY_EMAIL") or ""
    if not webhook and not email:
        return []
    sent = []
    for finding in found:
        if _already_told(finding):
            continue
        for channel, send, target in (("webhook", send_webhook, webhook), ("email", send_email, email)):
            if not target:
                continue
            try:
                send(target, finding)
            except Exception as error:  # noqa: BLE001 - one channel down is not the other
                logger.warning("Could not send the %s notice for %s: %s", channel, finding["run_id"], type(error).__name__)
        sent.append(finding)
    return sent


async def notify_what_is_stalled(runner: Any, now: datetime | None = None) -> list[dict[str, Any]]:
    """The sweep's step: find and send. Never raises."""
    try:
        records = runner.run_store.list_all(limit=500, offset=0)
        return notify(findings(records, now or datetime.now(timezone.utc)))
    except Exception:  # noqa: BLE001 - a sweep never takes the server down
        logger.warning("The stall sweep failed", exc_info=True)
        return []


__all__ = ["findings", "notify", "notify_what_is_stalled"]
