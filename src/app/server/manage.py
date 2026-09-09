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


def reconcile_runs(dry_run: bool = False) -> int:
    """Resync run rows whose recorded status disagrees with their graph state.

    The checkpointer is the authority on where a run actually is; the `runs`
    row is a cache of that, kept so the API can answer without reading a
    checkpoint on every request. A node that raised was never checkpointed, and
    the failure path used to record a flat "failed" without touching
    `current_stage` - leaving rows that said `failed` while the graph was still
    parked on an approval gate.

    Such a row is unreachable: the UI offers Resume because the status is
    failed, Resume cannot clear an approval gate, and /approve refuses anything
    whose status is not `waiting_for_approval`. The write path no longer creates
    these, but rows written before that fix still exist.
    """
    from app.graph.workflow import APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX
    from app.server.run_store import RunStore
    from app.server.runner import _api_status, _stage_meaning

    store = RunStore.shared()

    # `list_all` caps its page at 500, so walk pages rather than asking for a
    # number the store will quietly shrink.
    records: list = []
    offset = 0
    while True:
        page = store.list_all(limit=500, offset=offset)
        records.extend(page)
        if len(page) < 500:
            break
        offset += 500

    repaired = 0
    for record in records:
        stage = record.current_stage or ""
        # Only a *pause* can be inferred safely from a stale row. Every other
        # stage maps to "running", and a row is not evidence that a worker is
        # still alive - a genuinely failed run whose last stage was an ordinary
        # node must stay failed, not be resurrected as running.
        if not stage.startswith((APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX)):
            continue
        expected = _api_status(stage)
        if record.status == expected or record.status in ("cancelled", "completed"):
            continue

        print(f"{record.run_id}: {record.status} -> {expected}  (stage: {stage})")
        repaired += 1
        if dry_run:
            continue
        record.status = expected
        record.stage_meaning = _stage_meaning(stage)
        store.save(record)

    if not repaired:
        print("All runs agree with their graph state.")
    elif dry_run:
        print(f"\n{repaired} run(s) would be repaired. Re-run without --dry-run to apply.")
    else:
        print(f"\nRepaired {repaired} run(s).")
    return 0


def clear_run_overrides(run_id: str | None = None, dry_run: bool = False) -> int:
    """Drop per-run provider pins so runs inherit the current settings again.

    The UI used to copy the settings page's provider, model and base URL into
    every run it started, as "overrides". They were never a choice - that form
    has no control for picking a different model - so each run snapshotted
    whatever global config said at the moment it started, and the snapshot then
    outranked Settings forever. Changing the model or the endpoint afterwards
    could not reach a run that already existed.

    The UI no longer sends them. This clears the ones already written, which is
    safe precisely because every one of them is a copy rather than a decision.
    """
    from app.server.run_store import RunStore

    store = RunStore.shared()
    if run_id:
        record = store.load(run_id)
        if record is None:
            print(f"No run named '{run_id}'.", file=sys.stderr)
            return 1
        records = [record]
    else:
        records, offset = [], 0
        while True:
            page = store.list_all(limit=500, offset=offset)
            records.extend(page)
            if len(page) < 500:
                break
            offset += 500

    cleared = 0
    for record in records:
        if not record.model_overrides:
            continue
        print(f"{record.run_id}: clearing {record.model_overrides}")
        cleared += 1
        if dry_run:
            continue
        record.model_overrides = {}
        store.save(record)

    if not cleared:
        print("No run carries a provider pin.")
    elif dry_run:
        print(f"\n{cleared} run(s) would be cleared. Re-run without --dry-run to apply.")
    else:
        print(f"\nCleared {cleared} run(s); they now use the current settings.")
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

    reconcile = sub.add_parser(
        "reconcile-runs", help="Resync run rows that disagree with their graph state"
    )
    reconcile.add_argument("--dry-run", action="store_true", help="Report without changing anything")

    pins = sub.add_parser(
        "clear-run-overrides",
        help="Drop per-run provider pins so runs use the current settings",
    )
    pins.add_argument("run_id", nargs="?", help="One run; omit for every run")
    pins.add_argument("--dry-run", action="store_true", help="Report without changing anything")

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
    if args.command == "reconcile-runs":
        return reconcile_runs(args.dry_run)
    if args.command == "clear-run-overrides":
        return clear_run_overrides(args.run_id, args.dry_run)
    if args.command == "disable-user":
        return set_disabled(args.username, True)
    if args.command == "enable-user":
        return set_disabled(args.username, False)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
