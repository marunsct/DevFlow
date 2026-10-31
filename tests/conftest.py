"""Shared test fixtures.

Every database and cache the suite touches comes from a container started here.
The URLs are exported under *every* name the application reads before any app
module is imported, because several modules resolve their connection settings at
import time; exporting late would leave them bound to a default that points at
whatever happens to be listening on localhost.
"""

import faulthandler
import contextlib
import os

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


#: How long one test may take before the suite is treated as hung. Generous:
#: the slowest legitimate tests here start a container or drive a real agent
#: graph. Set `TEST_TIMEOUT_SECONDS=0` to switch it off.
DEFAULT_TEST_TIMEOUT_SECONDS = 180

# The whole-graph routing tests script technical-lead plans written before work
# orders existed, so the definition-of-ready check would send every one of them
# back. Off here; the tests that exercise it turn it on. See
# `app.analysis.work_orders.readiness_enforced`.
os.environ.setdefault("WORKFLOW_WORK_ORDER_READINESS", "off")
# At import, not in a session fixture: a test module that imports
# `app.server.auth` at its top level is collected before any fixture runs, and
# auth refuses to load without a key - whether it did depended on which worker
# collected which file first.
os.environ.setdefault("ENV", "development")
# No test reaches a real model. `load_settings` reads `.env` without overriding, so without this the suite took its
# model server from the operator's file: a run's startup path diagnoses the model, and when the file named a server
# that needs no key the tests sent it real requests, beside the live runs, and took minutes. Port 9 refuses at once;
# a test wanting an address sets its own.
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ["JUDGEMENT_BASE_URL"] = ""


@pytest.fixture(autouse=True)
def _the_built_in_fixes_at_their_code_default(monkeypatch):
    """Each built-in fix's old variable set off, as every test was written against: a test sets one on to test it.

    The base product has them always on (`app.switches.BUILT_IN`, owner 2026-10-29). The suite was written while each
    was a switch off in its code, and its tests turn on only the one they test; this keeps that. A test that sets
    a variable itself, or clears one to see the product's default, still does.
    """
    from app.switches import BUILT_IN

    for name in BUILT_IN:
        if name not in os.environ:
            monkeypatch.setenv(name, "off")
    yield


@pytest.fixture(autouse=True)
def _fail_a_hung_test():
    """Turn a hang into a stack trace that names the test.

    Two suite runs on 2026-09-23 sat for 32 and 11 minutes having used four
    and three seconds of CPU between them - blocked, not computing - and
    produced no output at all, because `-q` writes its summary only at the
    end. There was nothing to read and nothing to act on but a process id.

    A hang with no deadline is the worst shape a test failure can take. It
    stops the fix-test-deploy loop entirely, it looks identical to "slow", and
    the usual instinct - start another run to compare - is what turned one
    stuck suite into two.

    `faulthandler` rather than a plugin, because it needs no dependency and
    prints every thread's stack at the moment of the timeout, which is
    precisely what was missing. `exit=True` ends the process: a suite that has
    hung is not going to recover, and a named stack beats a silent wait.
    """
    seconds = int(os.environ.get("TEST_TIMEOUT_SECONDS", DEFAULT_TEST_TIMEOUT_SECONDS))
    if seconds > 0:
        faulthandler.dump_traceback_later(seconds, exit=True)
    try:
        yield
    finally:
        if seconds > 0:
            faulthandler.cancel_dump_traceback_later()


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


@pytest.fixture(scope="session", autouse=True)
def no_research_reaches_the_network():
    """The web search and the MCP Registry search stay off unless a test turns them on.

    A suite run built an agent with this repository as its workspace, and the
    registry search (`app.tools.mcp_registry`) read the repository's own
    manifest, asked PyPI and the registry from inside the tests, and wrote what
    it found into the source tree as `.harness/mcp-official.json`.
    """
    os.environ["HARNESS_MCP_DISCOVERY"] = "false"
    os.environ.pop("SEARXNG_URL", None)
    yield


@pytest.fixture(autouse=True)
def no_model_server_is_read(monkeypatch):
    """The model server's `/props` is never read from a test; a test that needs a profile sets one.

    The settings page reads the server afresh to name the served model
    (`steering_job.page_model`); from a test that would read the developer's
    own server, and its profile would be every later test's.
    """
    from app.models import server_profile

    monkeypatch.setattr(server_profile, "read", lambda *args, **kwargs: None)


@pytest.fixture(scope="session", autouse=True)
def an_openai_key_that_is_not_a_secret():
    """A dummy `OPENAI_API_KEY` for the tests that build a real client.

    The agent-factory tests pass model strings such as `"openai:gpt-4o-mini"`,
    and LangChain's `init_chat_model` reads the key straight from the process
    environment - not through `app.config`. They passed only because the
    developer's `.env` happened to hold a key: on 2026-09-28 a rebuilt `.env`
    left it blank and 37 tests failed with "Missing credentials" before any of
    them made a call. None of them goes to the network, so a dummy is all they
    need, and a dummy is safer than a real key - a test that did reach OpenAI
    would fail loudly rather than spend money. `.env` is loaded with
    `override=False`, so the dummy set here is what every test sees.
    """
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        os.environ["OPENAI_API_KEY"] = "sk-test-not-a-real-key"
    yield


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_endpoint_probe: keep the runner's model-server reachability gate in this test",
    )
    config.addinivalue_line(
        "markers",
        "real_execution_readiness: keep the runner's command-execution gate in this test",
    )


@pytest.fixture(autouse=True)
def no_model_server_needed(request, monkeypatch):
    """Tests that start a run must not need a live model server on this machine.

    `WorkflowRunner` refuses to start a run when nothing answers at the
    configured model endpoint. The lifecycle, API and seeding tests start runs
    and never call a model, yet they only passed while the developer's `.env`
    pointed at a server that happened to be up - on 2026-09-28 a rebuilt `.env`
    left the endpoint at its default, `localhost:1234`, and 10 of them failed
    with "Nothing is listening on localhost:1234". The probe itself is tested
    directly in `test_endpoint_probe.py`, which calls `describe_model_endpoint`
    and is not affected by this. A test that needs the gate in place marks
    itself `real_endpoint_probe`.
    """
    if request.node.get_closest_marker("real_endpoint_probe") is None:
        from app.server.runner import WorkflowRunner

        monkeypatch.setattr(WorkflowRunner, "_require_a_reachable_model", lambda self, *args, **kwargs: None)
    yield


@pytest.fixture(autouse=True)
def workers_can_run_commands(request, monkeypatch):
    """Tests that start a run must not depend on what a live worker recorded.

    `WorkflowRunner` refuses a run when the workers reported that commands
    cannot run (`app.server.execution_readiness`); that record lives in the
    deployment's Redis, not in the test. A test of the refusal marks itself
    `real_execution_readiness`.
    """
    if request.node.get_closest_marker("real_execution_readiness") is None:
        from app.server.runner import WorkflowRunner

        async def ready(self) -> None:
            return None

        monkeypatch.setattr(WorkflowRunner, "_require_command_execution", ready)
    yield


@pytest.fixture(autouse=True)
def no_reasoning_probe(monkeypatch):
    """Switching reasoning off measures the model server once (see
    `app.agents.thinking.least_reasoning_effort`). No test has a server to
    measure, so every one sees a server that honours "none" - what the harness
    sent before the measurement existed - and a cache of its own. The tests of
    the measurement replace `_reasoning_spent` themselves."""
    from app.agents import thinking

    monkeypatch.setattr(thinking, "_reasoning_spent", lambda model, effort: 0)
    monkeypatch.setattr(thinking, "_least_effort", {})
    yield


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



@contextlib.contextmanager
def metrics_kept_in_this_process():
    """Restore `prometheus_client`'s value class on the way out.

    `observability.metrics._prepare_multiprocess_dir` switches it to the
    multiprocess class when `PROMETHEUS_MULTIPROC_DIR` is set, for the life of
    the process. A test that set the variable (and had it removed after) left
    its xdist worker in that mode, and the next test there that built the app -
    any `client` test - failed creating its first metric with
    "expected str ... not NoneType": a different test each suite, passing alone.
    """
    try:
        from prometheus_client import values
    except ImportError:
        yield
        return
    before = values.ValueClass
    try:
        yield
    finally:
        values.ValueClass = before


@pytest.fixture(autouse=True)
def _metrics_stay_in_this_process():
    with metrics_kept_in_this_process():
        yield

@pytest.fixture(autouse=True)
def _no_model_router_outlives_its_test():
    """A router registered by one test must not be pinged by another.

    Building a chat model registers a router for its configuration, process-wide,
    and the model health endpoint pings every registered model for real. A test
    of that endpoint run after the tests that build models from this host's own
    settings sent requests to the operator's local model servers.
    """
    from app.models.router import ModelRouter

    ModelRouter.reset()
    yield
    ModelRouter.reset()


@pytest.fixture(autouse=True)
def _forget_what_stages_have_seen():
    """Per-stage memory must not carry from one test into the next.

    Both stores fall back to a module-level dict when there is no graph run to
    key on, which is every test. Without this, a test that reads "app.js" in
    its own tmp_path leaves a digest behind that the next test's "app.js"
    is compared against, and the stale-edit message fires on a file nothing
    changed.
    """
    from app.agents import stage_memory
    from app.tools import seen_content

    stage_memory.forget_everything()
    seen_content.forget_everything()
    yield
    stage_memory.forget_everything()
    seen_content.forget_everything()
