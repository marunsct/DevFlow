"""SQLite connection management and schema initialization."""

import os
import sqlite3
from typing import Generator

import bcrypt


# Expose DATA_DIR for tests and other modules to access directly
DATA_DIR = os.environ.get("DATA_DIR", "data")


def _get_data_dir() -> str:
    """Get the data directory from environment, evaluated at runtime."""
    return os.environ.get("DATA_DIR", "data")


def init_db(db_path: str) -> None:
    """Ensure parent directory exists, check/recreate the database file and schema.

    If the file does not exist or lacks expected tables, recreate it to ensure
    schema correctness. Creates accounts, items, and tokens tables.
    """
    # Ensure parent directory of db_path exists
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent_dir, exist_ok=True)

    # Determine if we need to create/recreate the database
    recreate = False
    if not os.path.exists(db_path):
        recreate = True
    else:
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                # Check for required tables (exclude internal SQLite tables)
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = {row[0] for row in cursor.fetchall()}
                # Filter out internal SQLite tables created by AUTOINCREMENT
                tables = {t for t in tables if not t.startswith('sqlite_')}
                if tables != {'accounts', 'items', 'tokens'}:
                    recreate = True
        except Exception:
            recreate = True

    if recreate:
        # Remove existing file if it exists to start fresh
        if os.path.exists(db_path):
            os.remove(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Create accounts table
            cursor.execute("""
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)

            # Create items table
            cursor.execute("""
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL REFERENCES accounts(id),
                    title TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0
                )
            """)

            # Create tokens table
            cursor.execute("""
                CREATE TABLE tokens (
                    token_hash TEXT PRIMARY KEY,
                    account_id INTEGER NOT NULL REFERENCES accounts(id)
                )
            """)

            conn.commit()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that yields a SQLite connection per request.

    Opens connection to DATA_DIR/tasks.db, sets WAL journal mode and 5s busy timeout.
    Closes connection when request ends.
    """
    data_dir = _get_data_dir()
    db_path = os.path.join(data_dir, "tasks.db")

    # Ensure database is initialized before yielding
    try:
        if not os.path.exists(db_path):
            init_db(db_path)
        else:
            with sqlite3.connect(db_path) as conn_check:
                cursor = conn_check.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = {row[0] for row in cursor.fetchall()}
                if tables != {'accounts', 'items', 'tokens'}:
                    init_db(db_path)
    except Exception as e:
        raise

    # check_same_thread=False is required because FastAPI runs sync endpoint
    # functions in a threadpool; the connection may be used across threads.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        yield conn
    finally:
        conn.close()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode(),
            password_hash.encode() if isinstance(password_hash, str) else password_hash
        )
    except Exception:
        return False


def create_token(conn: sqlite3.Connection, account_id: int, token_value: str) -> None:
    """Create a new token record in the database.
    
    Stores the hash of the token value for security.
    Uses SHA-256 to ensure consistent hashing across signin and lookup.
    """
    import hashlib
    token_hash = hashlib.sha256(token_value.encode()).hexdigest()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tokens (token_hash, account_id) VALUES (?, ?)",
        (token_hash, account_id)
    )
    conn.commit()


def get_account_id_by_token(conn: sqlite3.Connection, token_value: str):
    """Resolve account_id from a raw token value.
    
    Returns account_id if valid, None otherwise.
    Uses SHA-256 to ensure consistent hashing with create_token.
    """
    import hashlib
    token_hash = hashlib.sha256(token_value.encode()).hexdigest()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT account_id FROM tokens WHERE token_hash = ?",
        (token_hash,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def get_account_by_username(conn: sqlite3.Connection, username: str):
    """Get account record by username."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, password_hash FROM accounts WHERE username = ?",
        (username,)
    )
    return cursor.fetchone()


def create_account(conn: sqlite3.Connection, username: str, password: str) -> int:
    """Create a new account. Returns the account ID."""
    password_hash = hash_password(password)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # This should be handled at the route level for 409, but if it slips through:
        raise


def create_item(conn: sqlite3.Connection, account_id: int, title: str) -> dict:
    """Create a new item. Returns the created item dict."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO items (account_id, title, done) VALUES (?, ?, 0)",
        (account_id, title)
    )
    conn.commit()
    item_id = cursor.lastrowid
    return {"id": item_id, "title": title, "done": False}


def get_items_for_account(conn: sqlite3.Connection, account_id: int) -> list:
    """Get all items for an account, ordered by id ascending."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, done FROM items WHERE account_id = ? ORDER BY id ASC",
        (account_id,)
    )
    rows = cursor.fetchall()
    return [{"id": row[0], "title": row[1], "done": bool(row[2])} for row in rows]


def get_item(conn: sqlite3.Connection, item_id: int, account_id: int) -> dict:
    """Get a single item if it belongs to the account.
    
    Returns item dict or None.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, done FROM items WHERE id = ? AND account_id = ?",
        (item_id, account_id)
    )
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "title": row[1], "done": bool(row[2])}
    return None


def update_item(conn: sqlite3.Connection, item_id: int, account_id: int, done: bool) -> dict:
    """Update an item's done status. Returns updated item or None if not found/unauthorized."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE items SET done = ? WHERE id = ? AND account_id = ?",
        (int(done), item_id, account_id)
    )
    if cursor.rowcount == 0:
        return None
    
    # Fetch the updated item to return
    conn.commit()
    cursor.execute(
        "SELECT id, title, done FROM items WHERE id = ? AND account_id = ?",
        (item_id, account_id)
    )
    row = cursor.fetchone()
    if row:
        return {"id": row[0], "title": row[1], "done": bool(row[2])}
    return None


def delete_item(conn: sqlite3.Connection, item_id: int, account_id: int) -> bool:
    """Delete an item if it belongs to the account. Returns True if deleted."""
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM items WHERE id = ? AND account_id = ?",
        (item_id, account_id)
    )
    if cursor.rowcount == 0:
        return False
    
    conn.commit()
    return True
