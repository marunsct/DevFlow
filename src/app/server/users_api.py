"""People's accounts from the UI (LR.36): change your own password; an administrator lists, adds and disables users.

Found in the launch review: accounts were made and passwords reset only from the command line inside the container,
so a new deployment's second person, or a forgotten password, needed shell access to the server.
"""
from __future__ import annotations

import secrets
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.server.auth import (
    UserInDB,
    get_current_active_user,
    get_db_connection,
    get_password_hash,
    record_audit,
    require_admin,
    verify_password,
)

users_router = APIRouter(tags=["users"])

#: The shortest password a person may set.
SHORTEST_PASSWORD = 12


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=512)
    new_password: str = Field(..., min_length=SHORTEST_PASSWORD, max_length=512)


class NewUser(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    role: Literal["admin", "operator", "viewer"] = "operator"
    password: Optional[str] = Field(default=None, min_length=SHORTEST_PASSWORD, max_length=512)


class UserChange(BaseModel):
    role: Optional[Literal["admin", "operator", "viewer"]] = None
    disabled: Optional[bool] = None


def _set_password(username: str, password: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET hashed_password = %s WHERE username = %s", (get_password_hash(password), username))
        conn.commit()


@users_router.post("/api/auth/password")
async def change_password(body: PasswordChange, user: UserInDB = Depends(get_current_active_user)) -> dict[str, str]:
    """Change the signed-in person's own password, given the current one."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=403, detail="The current password is not right.")
    _set_password(user.username, body.new_password)
    record_audit(actor=user.username, tenant_id=user.tenant_id, action="user.password_change", subject=user.username)
    return {"message": "Password changed."}


@users_router.get("/api/users")
async def list_users(admin: UserInDB = Depends(require_admin)) -> list[dict]:
    """The users of the administrator's tenant."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, role, disabled FROM users WHERE tenant_id = %s ORDER BY username",
                        (admin.tenant_id,))
            rows = cur.fetchall()
    return [{"username": r[0], "role": r[1], "disabled": bool(r[2])} for r in rows]


@users_router.post("/api/users", status_code=201)
async def add_user(body: NewUser, admin: UserInDB = Depends(require_admin)) -> dict[str, str]:
    """Add a user to the administrator's tenant; a password is generated and shown once when none is given."""
    password = body.password or secrets.token_urlsafe(18)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username = %s", (body.username,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"A user named {body.username} already exists.")
            cur.execute("INSERT INTO users (username, hashed_password, disabled, role, tenant_id) VALUES (%s, %s, FALSE, %s, %s)",
                        (body.username, get_password_hash(password), body.role, admin.tenant_id))
        conn.commit()
    record_audit(actor=admin.username, tenant_id=admin.tenant_id, action="user.create", subject=body.username,
                 detail={"role": body.role})
    return {"username": body.username, "role": body.role, **({} if body.password else {"password": password})}


@users_router.patch("/api/users/{username}")
async def change_user(username: str, body: UserChange, admin: UserInDB = Depends(require_admin)) -> dict[str, str]:
    """Change a user's role, or disable or enable them; an administrator never disables or demotes themself."""
    if username == admin.username and (body.disabled or (body.role and body.role != "admin")):
        raise HTTPException(status_code=409, detail="You cannot disable or demote yourself.")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if body.role is not None:
                cur.execute("UPDATE users SET role = %s WHERE username = %s AND tenant_id = %s",
                            (body.role, username, admin.tenant_id))
            if body.disabled is not None:
                cur.execute("UPDATE users SET disabled = %s WHERE username = %s AND tenant_id = %s",
                            (body.disabled, username, admin.tenant_id))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"No user named {username}.")
        conn.commit()
    record_audit(actor=admin.username, tenant_id=admin.tenant_id, action="user.change", subject=username,
                 detail=body.model_dump(exclude_none=True))
    return {"message": f"{username} changed."}


__all__ = ["users_router"]
