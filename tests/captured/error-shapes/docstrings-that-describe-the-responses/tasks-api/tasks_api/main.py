"""The service's HTTP interface."""

import os
from typing import Generator

import argon2
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlite3 import Connection

from tasks_api import db
from tasks_api import auth
from tasks_api.models import SignupRequest, SigninRequest, ItemCreate, ItemUpdate, ItemResponse

app = FastAPI(title="Tasks API")

# Argon2ID hasher instance
argon_hasher = argon2.PasswordHasher()

# JWT Bearer scheme (auto_error=False to handle missing header manually)
security_scheme = HTTPBearer(auto_error=False)


def register_exception_handlers(app: FastAPI) -> None:
    """Registers a custom exception handler for RequestValidationError that strips Pydantic error details
    and returns HTTP 422 with {"detail": "Invalid request body"}. Adds a catch-all handler for unhandled
    exceptions returning HTTP 500 with {"detail": "Internal server error"}."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request body"}
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )


def get_db() -> Generator[Connection, None, None]:
    """FastAPI dependency called with Depends(get_db, scope='function').
    Reads os.environ['DATA_DIR'] to construct the database path.
    Calls db.get_connection, yields the connection, ensures db.close_connection is called in a finally block.

    NOTE: This is a plain generator (not decorated with @contextmanager). FastAPI's dependency injection
    iterates directly over generators; wrapping with @contextmanager produces a _GeneratorContextManager
    object which cannot be iterated and causes TypeError.
    """
    data_dir = os.environ['DATA_DIR']
    conn = db.get_connection(data_dir)
    try:
        yield conn
    finally:
        db.close_connection(conn)


def get_current_account_id(authorization: str | HTTPAuthorizationCredentials | None = Depends(security_scheme)) -> int:
    """FastAPI dependency. If authorization is None (missing header), raises HTTPException(401, "Missing token").

    FastAPI's HTTPBearer scheme with auto_error=False yields either:
      - None            when no Authorization header is present, or
      - HTTPAuthorizationCredentials  when a Bearer header IS present.

    The credentials object carries the raw token string in its .credentials attribute.
    We extract it here so jwt.decode() receives an actual str, not an object.
    """

    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing token")

    # Extract the raw token string from the credentials object (or use it directly if already a str)
    if isinstance(authorization, HTTPAuthorizationCredentials):
        token_string = authorization.credentials
    else:
        token_string = authorization

    data_dir = os.environ['DATA_DIR']
    key_path = db.get_signing_key_path(data_dir)

    try:
        with open(key_path, "rb") as f:
            key = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        payload = auth.decode_token(token_string, key)
        # The DB schema uses account_id (integer) as the account identifier.
        # The JWT payload stores it as {"id": str(account_id)}.
        return int(payload["id"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.on_event("startup")
def startup():
    """Startup initialization: call init_db() and ensure signing key exists."""
    data_dir = os.environ['DATA_DIR']
    conn = db.get_connection(data_dir)
    try:
        db.init_db(conn)
        db.ensure_signing_key(data_dir)
    finally:
        db.close_connection(conn)


@app.post("/signup", status_code=201)
def signup(request: SignupRequest, conn: Connection = Depends(get_db)) -> dict:
    """POST /signup handler. Checks for existing username. If exists, raises HTTPException(409).
    Hashes password with argon2id. Inserts account. Returns 201 with {"username": request.username}."""

    # Check if username exists
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM accounts WHERE username = ?", (request.username,))
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail="Username already exists")

    # Hash password
    password_hash = argon_hasher.hash(request.password)

    # Insert account
    cursor.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (request.username, password_hash)
    )
    conn.commit()

    return {"username": request.username}


@app.post("/signin", status_code=200)
def signin(request: SigninRequest, conn: Connection = Depends(get_db)) -> dict:
    """POST /signin handler. Queries username and password_hash. If mismatch or not found, raises HTTPException(401).
    Loads signing key. Calls create_token with account_id as identifier (matching DB schema where accounts.id is PK).
    Returns 200 with {"token": token_string}."""

    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM accounts WHERE username = ?", (request.username,))
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=401)

    account_id = row[0]
    stored_hash = row[1]

    # Verify password
    try:
        argon_hasher.verify(stored_hash, request.password)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(status_code=401)

    # Create token using account_id as the identifier (matches DB schema)
    data_dir = os.environ['DATA_DIR']
    key_path = db.get_signing_key_path(data_dir)

    with open(key_path, "rb") as f:
        key = f.read()

    token = auth.create_token(account_id=account_id, key=key)

    return {"token": token}


@app.post("/items", status_code=201)
def create_item(request: ItemCreate, conn: Connection = Depends(get_db), account_id: int = Depends(get_current_account_id)) -> dict:
    """POST /items handler. Inserts item with title and account_id. Returns 201."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO items (title, account_id) VALUES (?, ?)",
        (request.title, account_id)
    )
    conn.commit()

    # Fetch the created item to return it
    item_id = cursor.lastrowid
    cursor.execute("SELECT id, title, done FROM items WHERE id = ?", (item_id,))
    row = cursor.fetchone()

    return {"id": row[0], "title": row[1], "done": False}


@app.get("/items", status_code=200)
def list_items(conn: Connection = Depends(get_db), account_id: int = Depends(get_current_account_id)) -> list[dict]:
    """GET /items handler. Queries items where account_id matches, ordered by id ASC."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, done FROM items WHERE account_id = ? ORDER BY id ASC",
        (account_id,)
    )
    rows = cursor.fetchall()

    return [{"id": row[0], "title": row[1], "done": bool(row[2])} for row in rows]


@app.patch("/items/{item_id}", status_code=200)
def update_item(item_id: int, request: ItemUpdate, conn: Connection = Depends(get_db), account_id: int = Depends(get_current_account_id)) -> dict:
    """PATCH /items/{id} handler. Updates done status where id=item_id AND account_id=account_id."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE items SET done = ? WHERE id = ? AND account_id = ?",
        (request.done, item_id, account_id)
    )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404)

    conn.commit()

    cursor.execute("SELECT id, title, done FROM items WHERE id = ?", (item_id,))
    row = cursor.fetchone()

    return {"id": row[0], "title": row[1], "done": bool(row[2])}


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, conn: Connection = Depends(get_db), account_id: int = Depends(get_current_account_id)) -> None:
    """DELETE /items/{id} handler. Deletes where id=item_id AND account_id=account_id."""
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM items WHERE id = ? AND account_id = ?",
        (item_id, account_id)
    )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404)

    conn.commit()


@app.get("/health")
def health_check() -> dict:
    """GET /health handler. Returns 200 with {"status": "ok"}."""
    return {"status": "ok"}


# Initialize exception handlers and startup logic
register_exception_handlers(app)
