"""Shared test fixtures.

Every database and cache the suite touches comes from a container started here.
The URLs are exported under *every* name the application reads before any app
module is imported, because several modules resolve their connection settings at
import time; exporting late would leave them bound to a default that points at
whatever happens to be listening on localhost.
"""

import os

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session", autouse=True)
def postgres_container():
    with PostgresContainer("postgres:15-alpine") as postgres:
        db_url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        # DB_URL is the name RunStore and the checkpointer read; AUTH_DB_URL is
        # the one app.server.auth reads. Both must be set, and both must be set
        # before those modules are imported.
        os.environ["DB_URL"] = db_url
        os.environ["AUTH_DB_URL"] = db_url
        os.environ["RUNS_DB_URL"] = db_url
        os.environ["POSTGRES_DB_URI"] = db_url
        yield postgres


@pytest.fixture(scope="session", autouse=True)
def isolated_runtime_dirs(tmp_path_factory):
    """Keep run workspaces and uploads out of the source tree."""
    base = tmp_path_factory.mktemp("runtime")
    os.environ["DATA_DIR"] = str(base)
    os.environ["WORKFLOW_WORKSPACE_ROOT"] = str(base / "workspaces")
    os.environ["WORKFLOW_UPLOAD_DIR"] = str(base / "uploads")
    os.environ.setdefault("ENV", "development")
    os.environ.setdefault("CHECKPOINTER_TYPE", "memory")
    yield base


@pytest.fixture(autouse=True)
def object_store_isolation(tmp_path_factory):
    """Keep each test's object storage local, empty, and its own.

    `get_object_store` caches the store for the process, so without this a test
    that configures S3 leaves that store cached for every test after it.
    """
    from app.server.object_store import reset_object_store

    previous = os.environ.get("OBJECT_STORE_BUCKET")
    previous_path = os.environ.get("OBJECT_STORE_PATH")
    os.environ.pop("OBJECT_STORE_BUCKET", None)
    os.environ["OBJECT_STORE_PATH"] = str(tmp_path_factory.mktemp("objects"))
    reset_object_store()
    try:
        yield
    finally:
        reset_object_store()
        os.environ.pop("OBJECT_STORE_PATH", None)
        if previous is not None:
            os.environ["OBJECT_STORE_BUCKET"] = previous
        if previous_path is not None:
            os.environ["OBJECT_STORE_PATH"] = previous_path


@pytest.fixture(scope="session", autouse=True)
def redis_container():
    with RedisContainer("redis:7-alpine") as redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        os.environ["REDIS_URL"] = f"redis://{host}:{port}/0"
        yield redis_container


@pytest.fixture(scope="session", autouse=True)
def setup_db(postgres_container, redis_container):
    """Create the schema once per session, against the container above."""
    from app.server.auth import init_db as init_auth_db, reset_db_pool
    from app.server.run_store import RunStore

    reset_db_pool()
    init_auth_db()
    store = RunStore()
    try:
        yield
    finally:
        store.close()


@pytest.fixture
def test_db(setup_db):
    """Give each test a clean users table.

    Truncating before *and* after keeps a test that leaves rows behind from
    leaking into the next one regardless of which order pytest picks.
    """
    from app.server.auth import get_db_connection, init_db

    def _truncate() -> None:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE users")
            conn.commit()

    _truncate()
    init_db()  # recreate the default admin row
    yield
    _truncate()


@pytest.fixture
def run_store(setup_db):
    """A RunStore bound to the container, with its rows cleaned up afterwards."""
    from app.server.run_store import RunStore

    store = RunStore()
    with store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE runs")
        conn.commit()
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def test_user():
    """A concrete user object for dependency overrides.

    Overrides used to return a bare dict, which worked only because no handler
    looked at anything but the presence of the value. Now that authorisation
    reads `role` and `tenant_id`, the override has to be the real type.
    """
    from app.server.auth import UserInDB

    return UserInDB(
        username="testuser",
        hashed_password="x",
        disabled=False,
        role="admin",
        tenant_id="default",
    )


@pytest.fixture
def authed_app(setup_db, test_user):
    """A FastAPI app with authentication satisfied by `test_user`."""
    from app.server.api import create_app
    from app.server.auth import get_current_active_user, require_admin, require_operator

    app = create_app()

    async def _override():
        return test_user

    # Every auth dependency is overridden, not just the base one: the role
    # dependencies are separate callables and would otherwise still hit the DB.
    for dependency in (get_current_active_user, require_admin, require_operator):
        app.dependency_overrides[dependency] = _override
    return app


@pytest.fixture
def client(authed_app):
    from fastapi.testclient import TestClient

    with TestClient(authed_app) as test_client:
        yield test_client
