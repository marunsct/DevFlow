import os
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

import logging

logger = logging.getLogger(__name__)


def _is_development() -> bool:
    """Development is opt-in, never inferred.

    The previous logic failed *open*: it only demanded a real secret when
    ENV == "production", so every deployment that forgot to set ENV - including
    the shipped docker-compose - silently ran on an ephemeral key. Requiring an
    explicit ENV=development to relax the rule inverts that, so a missing or
    mistyped ENV now fails closed.
    """
    return os.environ.get("ENV", "").strip().lower() in {"dev", "development", "test", "testing"}


def _load_secret_key() -> str:
    configured = os.environ.get("JWT_SECRET_KEY", "").strip()
    if configured:
        if len(configured) < 32 and not _is_development():
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters. "
                "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        return configured
    if not _is_development():
        raise ValueError(
            "JWT_SECRET_KEY is not set. Set it to a random 32+ character value, or set "
            "ENV=development to allow an ephemeral per-process key for local work only."
        )
    ephemeral = secrets.token_hex(32)
    logger.warning(
        "No JWT_SECRET_KEY set and ENV is a development value. Generated an ephemeral key; "
        "every restart invalidates all sessions and multiple workers will reject each "
        "other's tokens. Do not use this configuration outside local development."
    )
    return ephemeral


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# A pre-computed hash of a value nobody can supply. verify_password is run
# against this when the username is unknown, so a missing user costs the same
# ~100ms of bcrypt as a wrong password and cannot be told apart by timing.
_DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode("utf-8")


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _db_url() -> str:
    """Resolve the database URL at call time, never at import time.

    Reading this eagerly at module scope bound the value before test fixtures or
    a late-loading secret could set it, and left the pool permanently pointed at
    a default that could not resolve.
    """
    return os.environ.get("AUTH_DB_URL", "postgresql://postgres:postgres@db:5432/langchain_auth")


_db_pool: Optional[pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def init_db_pool() -> None:
    """Create the connection pool. Called from the app lifespan, not on import.

    Raises rather than degrading: an API that cannot reach its user store cannot
    authenticate anyone, so starting up and failing every request is strictly
    worse than refusing to start.
    """
    global _db_pool
    with _pool_lock:
        if _db_pool is not None:
            return
        _db_pool = pool.ThreadedConnectionPool(1, 20, _db_url())
        logger.info("Auth database pool initialised")


def reset_db_pool() -> None:
    """Drop the pool so the next use rebuilds it against the current URL."""
    global _db_pool
    with _pool_lock:
        if _db_pool is not None:
            try:
                _db_pool.closeall()
            except Exception:  # noqa: BLE001 - teardown must not mask the real error
                logger.debug("Ignoring error while closing auth pool", exc_info=True)
            _db_pool = None


@contextmanager
def get_db_connection():
    """Borrow a connection, always returning it and never leaking a bad one."""
    global _db_pool
    if _db_pool is None:
        init_db_pool()
    conn = _db_pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _db_pool.putconn(conn)


def close_db_pool():
    reset_db_pool()
    logger.info("Database connection pool closed")


def init_db():
    """Create the schema and seed the default admin.

    Raises on failure: an auth store that could not be created will fail every
    request anyway, and a warning that scrolls past in the log is how the broken
    state stayed invisible before.
    """
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username        TEXT PRIMARY KEY,
                    hashed_password TEXT NOT NULL,
                    disabled        BOOLEAN NOT NULL DEFAULT FALSE,
                    role            TEXT NOT NULL DEFAULT 'operator',
                    tenant_id       TEXT NOT NULL DEFAULT 'default'
                )
                """
            )
            # Columns added after the first release; ADD COLUMN IF NOT EXISTS is
            # idempotent so this is safe to run on every start.
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'operator'")
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'")
            # A database created before roles existed has an 'admin' account that
            # the ADD COLUMN default would silently demote to 'operator',
            # locking every administrative action out of an upgraded install.
            c.execute("UPDATE users SET role = 'admin' WHERE username = 'admin' AND role = 'operator'")

            c.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id             BIGSERIAL PRIMARY KEY,
                    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    actor          TEXT,
                    tenant_id      TEXT,
                    action         TEXT NOT NULL,
                    subject        TEXT,
                    outcome        TEXT NOT NULL,
                    correlation_id TEXT,
                    detail         JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS audit_log_occurred_at_idx ON audit_log (occurred_at DESC)")
            c.execute("CREATE INDEX IF NOT EXISTS audit_log_actor_idx ON audit_log (actor)")

            c.execute("SELECT 1 FROM users WHERE username = 'admin'")
            if not c.fetchone():
                admin_password = os.environ.get("ADMIN_PASSWORD")
                if not admin_password:
                    if not _is_development():
                        raise ValueError(
                            "ADMIN_PASSWORD is not set. Set it to seed the initial admin account, "
                            "or set ENV=development to allow a generated one."
                        )
                    admin_password = secrets.token_urlsafe(24)
                    logger.warning(
                        "No ADMIN_PASSWORD set. Generated a random admin password for this "
                        "development database: %s",
                        admin_password,
                    )
                c.execute(
                    "INSERT INTO users (username, hashed_password, disabled, role, tenant_id) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    ("admin", get_password_hash(admin_password), False, "admin", "default"),
                )
        conn.commit()


def record_audit(
    *,
    actor: Optional[str],
    action: str,
    subject: Optional[str] = None,
    outcome: str = "success",
    tenant_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """Append one row to the audit trail.

    Auditing must never break the operation it is recording, so failures here are
    logged and swallowed - but they are logged at error, because a silent gap in
    an audit trail is itself a finding.
    """
    import json

    from app.server.context import get_correlation_id

    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO audit_log (actor, tenant_id, action, subject, outcome, "
                    "correlation_id, detail) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        actor,
                        tenant_id,
                        action,
                        subject,
                        outcome,
                        get_correlation_id(),
                        json.dumps(detail or {}),
                    ),
                )
            conn.commit()
    except Exception:  # noqa: BLE001
        logger.error("Failed to write audit record for action=%s subject=%s", action, subject, exc_info=True)


auth_router = APIRouter()


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class TokenData(BaseModel):
    username: Optional[str] = None


class User(BaseModel):
    username: str
    disabled: Optional[bool] = None
    role: str = "operator"
    tenant_id: str = "default"


class UserInDB(User):
    hashed_password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def get_user(username: str) -> Optional[UserInDB]:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute(
                "SELECT username, hashed_password, disabled, role, tenant_id "
                "FROM users WHERE username = %s",
                (username,),
            )
            row = c.fetchone()
            if row:
                return UserInDB(
                    username=row["username"],
                    hashed_password=row["hashed_password"],
                    disabled=bool(row["disabled"]),
                    role=row.get("role") or "operator",
                    tenant_id=row.get("tenant_id") or "default",
                )
    return None


def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.update(
        {
            "exp": now + expires_delta,
            "iat": now,
            "typ": token_type,
            "jti": secrets.token_urlsafe(16),
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return _create_token(data, expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_refresh_token(data: dict) -> str:
    return _create_token(data, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), "refresh")


def _decode(token: str, expected_type: str = "access") -> Optional[str]:
    """Return the subject of a valid token of the expected type, else None.

    The type check matters: without it a long-lived refresh token would be
    accepted anywhere an access token is, silently defeating the short access
    lifetime.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    username = _decode(token, "access")
    if username is None:
        raise credentials_exception
    user = get_user(username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    if current_user.disabled:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user


def require_role(*allowed: str):
    """Dependency factory gating a route on the caller's role.

    Roles are ordered: an admin satisfies any requirement, so routes only need to
    name the least-privileged role that may use them.
    """

    async def _check(current_user: UserInDB = Depends(get_current_active_user)) -> UserInDB:
        if current_user.role == "admin" or current_user.role in allowed:
            return current_user
        raise HTTPException(
            status_code=403,
            detail=f"This action requires one of these roles: {', '.join(sorted(set(allowed)))}.",
        )

    return _check


require_admin = require_role("admin")
require_operator = require_role("operator", "admin")


async def get_user_from_token(token: str) -> Optional[User]:
    if not token:
        return None
    username = _decode(token, "access")
    if username is None:
        return None
    try:
        user = get_user(username)
    except Exception:  # noqa: BLE001 - a DB blip must not look like a valid session
        logger.error("Failed to load user while validating token", exc_info=True)
        return None
    if user and not user.disabled:
        return user
    return None


@auth_router.post("/api/auth/token", response_model=Token, tags=["auth"])
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    from app.server.rate_limit import check_login_attempt, clear_login_attempts, register_failed_login

    client_ip = request.client.host if request.client else "unknown"
    if not check_login_attempt(form_data.username, client_ip):
        record_audit(
            actor=form_data.username, action="auth.login", outcome="rate_limited",
            detail={"client_ip": client_ip},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Wait a few minutes and try again.",
        )

    user = get_user(form_data.username)
    # Always spend the same bcrypt work whether or not the user exists, so a
    # missing account cannot be distinguished from a wrong password by timing.
    stored_hash = user.hashed_password if user else _DUMMY_HASH
    password_ok = verify_password(form_data.password, stored_hash)

    if user is None or not password_ok or user.disabled:
        register_failed_login(form_data.username, client_ip)
        record_audit(
            actor=form_data.username,
            action="auth.login",
            outcome="failure",
            detail={"client_ip": client_ip},
        )
        raise unauthorized

    clear_login_attempts(form_data.username, client_ip)
    claims = {"sub": user.username, "role": user.role, "tenant": user.tenant_id}
    record_audit(
        actor=user.username, tenant_id=user.tenant_id, action="auth.login",
        outcome="success", detail={"client_ip": client_ip},
    )
    return {
        "access_token": create_access_token(claims),
        "refresh_token": create_refresh_token({"sub": user.username}),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@auth_router.post("/api/auth/refresh", response_model=Token, tags=["auth"])
async def refresh_access_token(body: RefreshRequest):
    username = _decode(body.refresh_token, "refresh")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = get_user(username)
    if user is None or user.disabled:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    claims = {"sub": user.username, "role": user.role, "tenant": user.tenant_id}
    return {
        "access_token": create_access_token(claims),
        "refresh_token": create_refresh_token({"sub": user.username}),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@auth_router.get("/api/auth/me", response_model=User, tags=["auth"])
async def read_users_me(current_user: UserInDB = Depends(get_current_active_user)) -> User:
    return User(
        username=current_user.username,
        disabled=current_user.disabled,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
    )
