"""The lesson store over REST, for the Settings page (plan item AT).

Reading is for any signed-in user; approving or rejecting a lesson decides
what reaches every later run's prompts, so it is the administrator's.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.plugins import lessons as store
from app.server.auth import UserInDB, get_current_active_user, record_audit, require_admin

lessons_router = APIRouter(prefix="/api/lessons", tags=["lessons"])


@lessons_router.get("")
async def list_lessons(user: UserInDB = Depends(get_current_active_user)) -> dict[str, Any]:
    """Every lesson on record, proposals first, with the evidence each rests on."""
    order = {"proposed": 0, "approved": 1, "rejected": 2}
    found = sorted(store.load(), key=lambda lesson: (order.get(str(lesson.get("status")), 3), str(lesson.get("id"))))
    return {"lessons": found}


async def _decide(lesson_id: str, approved: bool, user: UserInDB) -> dict[str, Any]:
    try:
        lesson = store.decide(lesson_id, approved, by=user.username)
    except store.LessonError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        record_audit(actor=user.username, action="lesson.approve" if approved else "lesson.reject", subject=lesson_id, tenant_id=getattr(user, "tenant_id", None))
    except Exception:  # noqa: BLE001 - the decision stands if the audit line cannot be written
        pass
    return {"lesson": lesson}


@lessons_router.post("/{lesson_id}/approve")
async def approve_lesson(lesson_id: str, user: UserInDB = Depends(require_admin)) -> dict[str, Any]:
    return await _decide(lesson_id, True, user)


@lessons_router.post("/{lesson_id}/reject")
async def reject_lesson(lesson_id: str, user: UserInDB = Depends(require_admin)) -> dict[str, Any]:
    return await _decide(lesson_id, False, user)
