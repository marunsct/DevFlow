"""Administrative commands for user accounts.

Run inside the app container, e.g.:

    docker compose exec app python -m app.server.manage reset-password admin
    docker compose exec app python -m app.server.manage create-user alice --role operator
    docker compose exec app python -m app.server.manage list-users

Why this exists: ``init_db`` deliberately will not overwrite an existing admin
account, which is correct - a restart must not silently reset a password. But
that left no way back in if the password was lost, and the first release
generated one at random and only wrote it to a log line. This is that way back
in, and it is an operator action rather than an API route on purpose: password
resets should require access to the host, not a session.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from app.server.auth import (
    get_db_connection,
    get_password_hash,
    init_db_pool,
    record_audit,
)

VALID_ROLES = ("admin", "operator", "viewer")


def _generate_password() -> str:
    return secrets.token_urlsafe(24)


def reset_password(username: str, password: str | None) -> int:
    """Set a user's password, generating one if none is supplied."""
    new_password = password or _generate_password()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET hashed_password = %s WHERE username = %s",
                (get_password_hash(new_password), username),
            )
            if cur.rowcount == 0:
                print(f"No user named '{username}'.", file=sys.stderr)
                return 1
        conn.commit()

    record_audit(actor="cli", action="user.password_reset", subject=username)
    print(f"Password updated for '{username}'.")
    if password is None:
        print(f"New password: {new_password}")
    return 0


def create_user(username: str, password: str | None, role: str, tenant: str) -> int:
    if role not in VALID_ROLES:
        print(f"Role must be one of: {', '.join(VALID_ROLES)}", file=sys.stderr)
        return 1

    new_password = password or _generate_password()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                print(f"User '{username}' already exists.", file=sys.stderr)
                return 1
            cur.execute(
                "INSERT INTO users (username, hashed_password, disabled, role, tenant_id) "
                "VALUES (%s, %s, FALSE, %s, %s)",
                (username, get_password_hash(new_password), role, tenant),
            )
        conn.commit()

    record_audit(
        actor="cli", action="user.create", subject=username,
        tenant_id=tenant, detail={"role": role},
    )
    print(f"Created '{username}' with role '{role}' in tenant '{tenant}'.")
    if password is None:
        print(f"Password: {new_password}")
    return 0


def set_role(username: str, role: str) -> int:
    if role not in VALID_ROLES:
        print(f"Role must be one of: {', '.join(VALID_ROLES)}", file=sys.stderr)
        return 1
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role = %s WHERE username = %s", (role, username))
            if cur.rowcount == 0:
                print(f"No user named '{username}'.", file=sys.stderr)
                return 1
        conn.commit()
    record_audit(actor="cli", action="user.set_role", subject=username, detail={"role": role})
    print(f"'{username}' is now '{role}'.")
    return 0


def set_disabled(username: str, disabled: bool) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET disabled = %s WHERE username = %s", (disabled, username))
            if cur.rowcount == 0:
                print(f"No user named '{username}'.", file=sys.stderr)
                return 1
        conn.commit()
    action = "user.disable" if disabled else "user.enable"
    record_audit(actor="cli", action=action, subject=username)
    print(f"'{username}' is now {'disabled' if disabled else 'enabled'}.")
    return 0


def list_users() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, role, tenant_id, disabled FROM users ORDER BY username")
            rows = cur.fetchall()

    if not rows:
        print("No users.")
        return 0
    print(f"{'USERNAME':<24} {'ROLE':<10} {'TENANT':<16} STATUS")
    for username, role, tenant, disabled in rows:
        print(f"{username:<24} {role:<10} {tenant:<16} {'disabled' if disabled else 'active'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.server.manage", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    reset = sub.add_parser("reset-password", help="Set a user's password")
    reset.add_argument("username")
    reset.add_argument("--password", help="Password to set; generated if omitted")

    create = sub.add_parser("create-user", help="Create a user account")
    create.add_argument("username")
    create.add_argument("--password", help="Password to set; generated if omitted")
    create.add_argument("--role", default="operator", choices=VALID_ROLES)
    create.add_argument("--tenant", default="default")

    role_cmd = sub.add_parser("set-role", help="Change a user's role")
    role_cmd.add_argument("username")
    role_cmd.add_argument("role", choices=VALID_ROLES)

    sub.add_parser("list-users", help="List all accounts")

    disable = sub.add_parser("disable-user", help="Disable an account")
    disable.add_argument("username")

    enable = sub.add_parser("enable-user", help="Re-enable an account")
    enable.add_argument("username")

    args = parser.parse_args(argv)
    init_db_pool()

    if args.command == "reset-password":
        return reset_password(args.username, args.password)
    if args.command == "create-user":
        return create_user(args.username, args.password, args.role, args.tenant)
    if args.command == "set-role":
        return set_role(args.username, args.role)
    if args.command == "list-users":
        return list_users()
    if args.command == "disable-user":
        return set_disabled(args.username, True)
    if args.command == "enable-user":
        return set_disabled(args.username, False)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
