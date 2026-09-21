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

import logging
import os

import argparse
from typing import Callable
import secrets
import sys

from app.server.auth import (
    get_db_connection,
    get_password_hash,
    init_db_pool,
    record_audit,
)

VALID_ROLES = ("admin", "operator", "viewer")


logger = logging.getLogger(__name__)


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
    from app.server.runner import _stage_narration

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
        # An unattended run answers its own gates, so a row that says
        # `awaiting_approval:...` is not evidence that anything is waiting. This
        # command used to call `_api_status` directly and would set such a row to
        # `waiting_for_approval` - which is the exact row state that lets
        # `submit_approval`'s compare-and-set pass and puts a second Celery task
        # on a thread the first is still driving.
        expected_meaning, expected = _stage_narration(
            stage, auto_approve=bool(record.auto_approve)
        )
        if record.status == expected or record.status in ("cancelled", "completed"):
            continue

        # A run repaired out of the F-0 damage was deliberately marked `failed`
        # while its stage still names a gate. Do not undo that: its checkpoint
        # history may have had two concurrent writers, and the whole point of
        # marking it failed was to stop it being resumed.
        if record.auto_approve and record.status == "failed":
            print(f"{record.run_id}: leaving failed (unattended run, repaired out of band)")
            continue

        print(f"{record.run_id}: {record.status} -> {expected}  (stage: {stage})")
        repaired += 1
        if dry_run:
            continue
        record.status = expected
        record.stage_meaning = expected_meaning
        store.save(record)

    if not repaired:
        print("All runs agree with their graph state.")
    elif dry_run:
        print(f"\n{repaired} run(s) would be repaired. Re-run without --dry-run to apply.")
    else:
        print(f"\nRepaired {repaired} run(s).")
    return 0


def _live_task_ids() -> set[str] | None:
    """Task ids the broker still knows about, or None if it cannot be asked.

    Active, reserved and scheduled together: a task that has been handed to a
    worker but not started yet is every bit as alive as one mid-execution, and
    resurrecting its run would put a second writer on the same thread.

    Returning None rather than an empty set when the broker is unreachable is
    the whole safety property here. An empty set means "nothing is running";
    None means "cannot tell", and the caller must do nothing rather than treat
    silence as permission.
    """
    try:
        from app.server.tasks import celery_app

        inspector = celery_app.control.inspect(timeout=5)
        live: set[str] = set()
        seen_a_worker = False
        for probe in (inspector.active, inspector.reserved, inspector.scheduled):
            replies = probe() or {}
            if replies:
                seen_a_worker = True
            for entries in replies.values():
                for entry in entries or []:
                    task_id = entry.get("id") or (entry.get("request") or {}).get("id")
                    if task_id:
                        live.add(task_id)
        return live if seen_a_worker else None
    except Exception as exc:  # noqa: BLE001 - unreachable broker must not repair anything
        print(f"Could not ask the broker which tasks are alive: {exc}")
        return None


def _worker_ran_out_of_memory() -> bool:
    """Whether this worker container has been OOM-killed. Never raises.

    An OOM kill is invisible from the run's side: Celery reports
    `WorkerLostError: signal 9`, the row stays `running`, and the generic
    "the container went away" message sends the operator looking for an
    infrastructure fault that did not happen.

    Measured on run-cbd22a34: `npx vitest run` forked one worker per CPU, each
    permitted `SANDBOX_MEMORY_LIMIT` of heap by RLIMIT_DATA, and the tree
    reached `memory.peak = 4,294,975,488` - exactly the container's limit. The
    kernel killed the Celery workers mid-test. Per-process rlimits do not bound
    a process tree, so the container limit is the real ceiling and the run died
    without anything naming the cause.
    """
    for path in ("/sys/fs/cgroup/memory.events", "/sys/fs/cgroup/memory/memory.oom_control"):
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    name, _, value = line.partition(" ")
                    if name in {"oom_kill", "oom_kill_disable"} and value.strip().isdigit():
                        if name == "oom_kill" and int(value) > 0:
                            return True
        except OSError:
            continue
    return False


#: Marks a run this process has already carried back onto the queue, so a
#: run whose worker dies again is recovered again but resumed only once. A
#: run that kills its worker every time it starts would otherwise restart for
#: ever, and each restart costs the whole stage.
_RESUMED_ON_START: set[str] = set()


def resume_runs_a_restart_abandoned(run_ids: list[str]) -> int:
    """Put runs their worker abandoned back on the queue. Never raises.

    `recover_orphaned_runs` marks such a run `failed`, which is what makes it
    reachable again - and then nothing reaches it. Measured over this
    session's own work: four worker restarts, four runs correctly recovered,
    four manual `POST /api/runs/<id>/resume` calls to carry each one forward.
    A deploy is not an exceptional event in this system; it happens on every
    configuration change and every code change, and a run lasts hours.

    Safety comes from three places and none of them is a timeout:

    * `recover_orphaned_runs` has already established that no worker claims
      the task, which is the property that stops two writers on one thread.
    * A run is resumed at most once per worker process. A run that kills its
      worker on every attempt is recovered every time and resumed the first
      time only, so a crash loop costs one repeat rather than an unbounded
      number.
    * An OOM-killed worker resumes nothing. The cause is the run's own memory
      use, restarting it repeats the kill, and the operator needs to see the
      message rather than watch it loop.

    Returns how many were queued.
    """
    if os.environ.get("RESUME_ORPHANS_ON_START", "true").strip().lower() in {
        "0", "false", "no", "off",
    }:
        return 0
    if _worker_ran_out_of_memory():
        logger.warning(
            "This worker has been OOM-killed, so %d recovered run(s) were left "
            "failed rather than resumed: restarting them repeats the kill. "
            "Raise the worker's memory limit or lower SANDBOX_MEMORY_LIMIT.",
            len(run_ids),
        )
        return 0

    queued = 0
    for run_id in run_ids:
        if run_id in _RESUMED_ON_START:
            logger.warning(
                "Run %s was already resumed once by this worker and its worker "
                "stopped again; leaving it failed so a crash loop cannot run "
                "for ever.", run_id,
            )
            continue
        _RESUMED_ON_START.add(run_id)
        try:
            _resume_one(run_id)
            queued += 1
            logger.info("Resumed run %s, abandoned by a worker that stopped", run_id)
        except Exception:  # noqa: BLE001 - one bad run must not block the rest
            logger.warning("Could not resume run %s", run_id, exc_info=True)
    return queued


def _resume_one(run_id: str) -> None:
    """Hand one run back to this process's runner.

    The runner is built per worker process by `tasks._init_worker_process`,
    and `tasks._get_runner` returns it - building it if the signal did not
    fire, which is the case this sweep runs in. There is no class-level
    accessor; an earlier version of this function invented one, its unit test
    supplied a double that had it, and the double was the only place it
    existed. The failure reached the worker log and not the suite.
    """
    import asyncio

    from app.server.tasks import _get_runner

    asyncio.run(_get_runner().resume_run(run_id))


def recover_orphaned_runs(
    dry_run: bool = False, emit: Callable[[str], None] = print
) -> int:
    """Return runs whose worker died to a state that can be resumed.

    `emit` is where the narration goes. It defaults to `print` because this is a
    CLI command first, but the worker calls it too, on a startup thread - and
    Celery's `redirect_stdouts` captures `print` at WARNING, so the healthy
    outcome ("No orphaned runs; every running row has a live task") was arriving
    in the log as a warning on every single worker start. A line that means
    "everything is fine", logged at the level reserved for things that are not,
    is how a log stops being read.

    A run is handed to one Celery task, and the row says `running` for as long
    as that task lives. If the process dies without unwinding - the host loses
    power, the container is replaced mid-task, the worker is killed - nothing
    ever writes a terminal status, and the row says `running` forever.

    Such a row has no way forward. `resume_run` compare-and-sets from `failed`,
    so it refuses; `reconcile-runs` only repairs rows parked on a pause and
    deliberately leaves unattended runs alone. The work is all still there - the
    graph checkpoints at every node boundary - but nothing can reach it.

    Marking the run `failed` is what makes it reachable again: resume then picks
    up from the last checkpoint and re-runs only the node that was interrupted.

    Safety rests on the broker, not on a timeout. A run is only touched when a
    worker answered and did not claim its task; if no worker answers at all, or
    the broker cannot be reached, nothing is repaired - guessing wrong here puts
    two writers on one thread, which is the damage `UNRESUMABLE_ERROR_MARKER`
    exists to mark.
    """
    from datetime import datetime, timezone

    from app.server.run_store import RunStore

    oom_killed = _worker_ran_out_of_memory()
    live = _live_task_ids()
    if live is None:
        emit("No worker answered, so nothing can be judged orphaned. Nothing changed.")
        return 1

    store = RunStore.shared()
    records: list = []
    offset = 0
    while True:
        page = store.list_all(limit=500, offset=offset)
        records.extend(page)
        if len(page) < 500:
            break
        offset += 500

    repaired = 0
    recovered: list[str] = []
    for record in records:
        if record.status != "running":
            continue
        if record.task_id and record.task_id in live:
            continue
        emit(f"{record.run_id}: running -> failed  (stage: {record.current_stage or '?'})")
        repaired += 1
        if dry_run:
            continue
        record.status = "failed"
        record.error = (
            "The worker running this stage stopped without finishing - the host or "
            "the container went away mid-task. Nothing was lost: resume continues "
            "from the last checkpoint and repeats only the interrupted step."
            + (
                "\n\nThis worker container has been OOM-killed at least once, so "
                "that is the likely cause. A test runner that forks a worker per "
                "CPU can exceed the container's memory limit while every single "
                "process stays inside SANDBOX_MEMORY_LIMIT - per-process rlimits "
                "do not bound a process tree. Raise the worker's memory limit, "
                "lower SANDBOX_MEMORY_LIMIT, or choose a test runner that does "
                "not fork (`node --test` rather than vitest or jest)."
                if oom_killed
                else ""
            )
        )
        record.updated_at = datetime.now(timezone.utc).isoformat()
        store.save(record)
        recovered.append(record.run_id)

    if repaired and oom_killed:
        emit(
            "\nThis worker container has been OOM-killed; that is the likely cause. "
            "See the runs' error text for what to change."
        )
    if not repaired:
        emit("No orphaned runs; every running row has a live task.")
    elif dry_run:
        emit(f"\n{repaired} run(s) would be recovered. Re-run without --dry-run to apply.")
    else:
        queued = resume_runs_a_restart_abandoned(recovered)
        if queued:
            emit(f"\nRecovered {repaired} run(s) and resumed {queued} of them.")
        else:
            emit(f"\nRecovered {repaired} run(s). Resume them to continue.")
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

    orphans = sub.add_parser(
        "recover-orphans",
        help="Make runs resumable whose worker died without finishing",
    )
    orphans.add_argument("--dry-run", action="store_true", help="Report without changing anything")

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
    if args.command == "recover-orphans":
        return recover_orphaned_runs(args.dry_run)
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
