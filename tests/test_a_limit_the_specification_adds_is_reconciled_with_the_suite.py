"""A limit the specification sets on how often one client may call is reconciled with the suite before the lock (LF.1269).

Measured on one medium-brief run: the brief asked for no rate limit; a security specialist's advice was adopted into
the specification ("registration attempts exceed 10 per hour per IP", "login attempts exceed 5 per minute per IP");
the locked suite signed up about 88 times and signed in about 92 times a run from one address against one service, and
every test past the tenth sign-up was refused 429 for 22 hours. A fixer named the collision and could do nothing: the
specification mandated it and the suite was locked.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import client_limits
from app.agents import specification_rulings
from tests.the_acceptance_review import PASSED, a_service_suite, measured, reviewed

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The specification's two limits as the measured run wrote them.
SECURITY = [
    "Passwords are hashed with bcrypt; tokens are signed JWTs.",
    "Return 429 Too Many Requests when registration attempts exceed 10 per hour per IP.",
    "Return 429 when login attempts exceed 5 per minute per IP.",
]

#: The measured suite's shape: one shared helper that signs up and signs in, called by every test.
HELPERS = """const BASE = '/api';
export async function registerAndLogin(request, name = `user${Date.now()}`) {
  const registered = await request.post(`${BASE}/auth/register`, { data: { email: `${name}@x.io`, password: 'pw123456' } });
  if (registered.status() === 429) throw new Error('Register rate limited');
  const signedIn = await request.post(`${BASE}/auth/login`, { data: { email: `${name}@x.io`, password: 'pw123456' } });
  if (!signedIn.ok()) throw new Error(`Login failed with status ${signedIn.status()}`);
  return (await signedIn.json()).access_token;
}
"""
A_TEST = """test('[AC-1] keeps record {n}', async ({{ request }}) => {{
  const token = await registerAndLogin(request);
  const made = await request.post('/api/items', {{ data: {{ title: 'a' }}, headers: {{ Authorization: `Bearer ${{token}}` }} }});
  expect(made.status()).toBe(201);
}});
"""


def a_spec_file(tests: int, first: int = 0) -> str:
    return ("import { test, expect } from '@playwright/test';\nimport { registerAndLogin } from './helpers.js';\n"
            + "".join(A_TEST.format(n=first + n) for n in range(tests)))


def the_measured_suite(tests: int = 88) -> dict[str, str]:
    """The suite's files by name: a helper module and two spec files whose every test signs up and signs in."""
    return {"acceptance/helpers.js": HELPERS, "acceptance/items.spec.js": a_spec_file(tests // 2),
            "acceptance/more.spec.js": a_spec_file(tests - tests // 2, first=tests // 2)}


def a_workspace_with(root: Path, files: dict[str, str]) -> Path:
    a_service_suite(root, files["acceptance/items.spec.js"], name="items.spec.js")
    for name, text in files.items():
        (root / "notes" / name).write_text(text, encoding="utf-8")
    return root


def a_state(root: Path, security: list[str], brief: str = "") -> dict:
    return {"repository": SimpleNamespace(root_path=str(root)), "document": SimpleNamespace(text=brief),
            "technical_specification": SimpleNamespace(security_and_privacy=security, interface_contract=[])}


def test_the_measured_limits_and_suite_are_one_finding_naming_both_limits():
    found = client_limits.collisions("\n".join(SECURITY), the_measured_suite())

    assert [(c.limit.count, c.limit.window, c.total) for c in found] == [(10, 3600, 88), (5, 60, 88)]
    assert [c.called for c in found] == ["${BASE}/auth/register", "${BASE}/auth/login"]
    finding = client_limits.the_finding(found, asked=False, start="`notes/playwright.config.js`")
    assert "registration attempts exceed 10 per hour per IP" in finding
    assert "login attempts exceed 5 per minute per IP" in finding
    assert "declined for this release" in finding and "CLIENT_RATE_LIMIT" in finding
    assert "`notes/playwright.config.js`" in finding


def test_one_sentence_limiting_two_routes_limits_each_of_them():
    """Measured on a second medium run: "Middleware applied to /api/auth/login and /api/auth/register. 5 requests per
    minute per IP address." Only the first route was read, so the suite's eleven sign-ups a minute were never
    compared with it."""
    spec = ("Rate limiting: Middleware applied to /api/auth/login and /api/auth/register. "
            "5 requests per minute per IP address.")
    suite = {"acceptance/helpers.js": HELPERS, "acceptance/items.spec.js": a_spec_file(12)}

    assert sorted(limit.route for limit in client_limits.limits_in(spec)) == ["/api/auth/login", "/api/auth/register"]
    found = client_limits.collisions(spec, suite)
    assert "${BASE}/auth/register" in [c.called for c in found]


def test_the_review_rules_for_the_specification_and_sends_the_suite_s_writers_nothing_of_it(tmp_path):
    root = a_workspace_with(tmp_path, the_measured_suite())
    spec = SimpleNamespace(security_and_privacy=SECURITY, interface_contract=[])

    update, _ = reviewed(root, measured(PASSED), specification=spec)

    asked = [d for d in update.get("decisions") or [] if "how often one client may call" in d.get("question", "")]
    assert len(asked) == 1
    assert not any("how often one client may call" in str(item) for item in update.get("acceptance_feedback") or [])
    section = specification_rulings.the_rulings_section(str(root))
    assert "registration attempts exceed 10 per hour per IP" in section and "declined for this release" in section
    assert "`notes/playwright.config.js`" in section
    assert not BANNED.search(section)
    assert client_limits.environment(root) == {"CLIENT_RATE_LIMIT": "1000"}


def test_a_second_review_adds_no_second_ruling(tmp_path):
    root = a_workspace_with(tmp_path, the_measured_suite())
    spec = SimpleNamespace(security_and_privacy=SECURITY, interface_contract=[])
    reviewed(root, measured(PASSED), specification=spec)

    again, _ = reviewed(root, measured(PASSED), specification=spec)

    assert not any("how often one client may call" in d.get("question", "") for d in again.get("decisions") or [])
    rulings = json.loads((root / specification_rulings.RULINGS_FILE).read_text(encoding="utf-8"))["rulings"]
    assert len(rulings) == 1


def test_a_brief_that_asks_for_a_limit_keeps_it_with_its_count_from_the_environment(tmp_path):
    root = a_workspace_with(tmp_path, the_measured_suite())
    update: dict = {}

    finding = client_limits.reconcile_before_the_lock(
        a_state(root, SECURITY, brief="Sign-in is rate limited to stop password guessing."), update)

    assert "The brief asks for this limit, so it stays" in finding and "`CLIENT_RATE_LIMIT=1000`" in finding
    assert "CLIENT_RATE_LIMIT" in specification_rulings.the_rulings_section(str(root))


def test_a_test_command_gives_the_product_the_count_the_ruling_names_and_no_other_command_does(tmp_path, monkeypatch):
    from app.tools import sandbox

    root = a_workspace_with(tmp_path, the_measured_suite())
    client_limits.reconcile_before_the_lock(a_state(root, SECURITY), {})
    given: dict[str, dict] = {}

    def run(argv, **kwargs):
        given[argv[-1]] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree", run)
    monkeypatch.setattr(sandbox.SandboxExecutor, "_resolve_executable", staticmethod(lambda name, *a, **k: "/usr/bin/" + name))
    sandbox.SandboxExecutor._execute_here(["npm", "test"], str(root), "testing_specialist", "test", 30, None)
    sandbox.SandboxExecutor._execute_here(["npm", "build"], str(root), "testing_specialist", "build", 30, None)

    assert given["test"]["CLIENT_RATE_LIMIT"] == "1000"
    assert "CLIENT_RATE_LIMIT" not in given["build"]


def test_a_limit_the_suite_fits_within_is_no_finding(tmp_path):
    root = a_workspace_with(tmp_path, the_measured_suite())
    roomy = ["Return 429 when registration attempts exceed 1000 per hour per IP.",
             "Return 429 when login attempts exceed 5 per minute per user."]

    assert client_limits.collisions("\n".join(roomy), the_measured_suite()) == []
    assert client_limits.reconcile_before_the_lock(a_state(root, roomy), {}) == ""
    assert client_limits.environment(root) == {}


def test_a_specification_with_no_limit_is_left_as_it_was(tmp_path):
    root = a_workspace_with(tmp_path, the_measured_suite())

    update, _ = reviewed(root, measured(PASSED), specification=SimpleNamespace(
        security_and_privacy=SECURITY[:1], interface_contract=[]))

    assert not any("how often one client may call" in d.get("question", "") for d in update.get("decisions") or [])
    assert not (root / client_limits.RECORD_FILE).exists()
    assert specification_rulings.the_rulings_section(str(root)) == ""


@pytest.mark.parametrize("prose", [
    "The dashboard shows the completion rate per day.",
    "The error rate is logged every 5 minutes.",
    "Rate limiting is out of scope for this release.",
    "Access tokens expire after 1 hour.",
    "Keep the error rate below 1% per hour.",
    "Lists show at most 50 items per page.",
    "Retry a failed write 3 times per minute.",
    "After 5 failed login attempts the account is locked for 15 minutes.",
])
def test_prose_that_only_mentions_a_rate_or_a_window_sets_no_limit(prose):
    assert client_limits.limits_in(prose) == []


@pytest.mark.parametrize("sentence, count, window, per, names", [
    ("Return 429 when registration attempts exceed 10 per hour per IP.", 10, 3600, "address", "/api/auth/register"),
    ("Rate-limit POST /api/auth/login to 5/min per user.", 5, 60, "user", "/v1/auth/login"),
    ("Sign-in is limited to 20 attempts per 15 minutes.", 20, 900, "address", "/sessions/signin"),
    ("Allow at most 100 requests per minute per IP address.", 100, 60, "address", None),
])
def test_a_limit_is_read_with_its_count_window_client_and_operation(sentence, count, window, per, names):
    [limit] = client_limits.limits_in(sentence)
    matcher = client_limits.address_matcher(limit)

    assert (limit.count, limit.window, limit.per) == (count, window, per)
    assert (matcher is None) == (names is None)
    assert names is None or (matcher(names) and not matcher("/api/items"))


def test_the_javascript_reader_counts_hooks_fixtures_loops_and_skips():
    from app.stacks.packs import _javascript

    suite = """import { test as base, expect } from '@playwright/test';
const LOGIN = '/api/auth/login';
const test = base.extend({ account: async ({ request }, use) => { await request.post(LOGIN, {}); await use(1); } });
test.beforeEach(async ({ request }) => { await request.post('/api/auth/login', {}); });
test.beforeAll(async ({ request }) => { await request.post('/api/auth/login', {}); });
test('[AC-1] six sign-ins', async ({ request }) => {
  for (let i = 0; i < 6; i++) { await request.post(LOGIN, {}); }
});
test('[AC-2] with the account', async ({ request, account }) => { await request.get('/api/items'); });
test.skip('[AC-3] not run', async ({ request }) => { await request.post(LOGIN, {}); });
"""
    per_test, once = _javascript.client_calls([suite], lambda text: text.endswith("/auth/login"))

    assert (per_test, once) == ([7, 2], 1)


def test_the_python_reader_counts_helpers_fixtures_and_loops():
    from app.stacks.packs import _python

    suite = '''import pytest
REGISTER = "/api/auth/register"

def sign_up(client):
    """Signs up at /api/auth/register."""
    return client.post(REGISTER, json={})

@pytest.fixture
def account(client):
    return sign_up(client)

def test_ac1_twelve_sign_ups(client):
    for _ in range(12):
        sign_up(client)

def test_ac2_with_an_account(client, account):
    assert client.get(f"/api/items").status_code == 200

@pytest.mark.skip(reason="later")
def test_ac3_not_run(client):
    sign_up(client)
'''
    per_test, once = _python.client_calls([suite], lambda text: text.endswith("/auth/register"))

    assert (per_test, once) == ([12, 1], 0)


def test_the_decision_text_avoids_the_banned_words():
    text = "\n".join([client_limits.the_decision(asked=True, start="`a`", value=1000),
                      client_limits.the_decision(asked=False, start="`a`", value=1000)])
    assert not BANNED.search(text)
