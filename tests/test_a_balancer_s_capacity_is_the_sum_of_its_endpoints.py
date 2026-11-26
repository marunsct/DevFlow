"""Behind a load balancer the model server's capacity is the pool's, not the one instance that answers `/props`.

Measured: two llama.cpp instances, each started with one slot, behind one balancer served two requests at once; but
`/props` read through the balancer is answered by one instance, so readiness said "1 slot(s); parallel mode and a
second run will wait their turn", and the parallel waves, fan-outs and the model call gate were all sized to one.
Earlier two instances of two slots each read as two, not four.

The balancer's status page and an instance's `/props` here are the real answers, captured from olla over two
llama.cpp instances (`tests/captured/`).
"""
from __future__ import annotations

import ast
import copy
import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import server_profile

#: The real reader: the suite's conftest replaces `read` for every test so none reads a developer's own server.
REAL_READ = server_profile.read

ROOT = Path(__file__).resolve().parents[1]
CAPTURED = ROOT / "tests" / "captured"
STATUS = json.loads((CAPTURED / "olla-status-endpoints-two-llama-cpp-instances.json").read_text())
PROPS = json.loads((CAPTURED / "llama-cpp-props-one-slot-behind-a-balancer.json").read_text())

BASE = "http://host.docker.internal:4001/olla/openai/v1/"
MODEL = "inkling-2-mini"


def _props(slots: int = 1, n_ctx: int | None = None, alias: str | None = None, path: str | None = None) -> dict:
    body = copy.deepcopy(PROPS)
    body["total_slots"] = slots
    if n_ctx is not None:
        body["default_generation_settings"]["n_ctx"] = n_ctx
    if alias is not None:
        body["model_alias"] = alias
    if path is not None:
        body["model_path"] = path
    return body


def _status(*statuses: str) -> dict:
    body = copy.deepcopy(STATUS)
    for entry, status in zip(body["endpoints"], statuses):
        entry["status"] = status
    return body


class Network:
    """The machine as the reader sees it: each address answers its body, a 404, or nothing."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.asked: list[tuple[str, dict[str, str]]] = []

    def urlopen(self, request, timeout=None):
        url = request.full_url
        self.asked.append((url, dict(request.header_items())))
        if url not in self.answers:
            raise urllib.error.URLError("connection refused")
        body = self.answers[url]
        if body == 404:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"404 page not found"))
        return io.BytesIO(json.dumps(body).encode())


def _balancer(status: dict | None = None, first: dict | None = None, second: dict | None = None) -> dict[str, object]:
    """Olla at the host's port 4001 over the instances it lists at 127.0.0.1:2001 and :2002."""
    first = first if first is not None else _props()
    return {
        "http://host.docker.internal:4001/olla/openai/props": first,
        "http://host.docker.internal:4001/internal/status/endpoints": status if status is not None else _status(),
        "http://host.docker.internal:2001/props": first,
        "http://host.docker.internal:2002/props": second if second is not None else _props(),
    }


@pytest.fixture
def network(monkeypatch):
    def install(answers: dict[str, object]) -> Network:
        net = Network(answers)
        monkeypatch.setattr(urllib.request, "urlopen", net.urlopen)
        return net

    def forget():
        server_profile._WITHOUT_PROPS.clear()
        try:
            from app.models import balancer
        except ImportError:  # the code before the balancer was read
            return
        balancer.forget()

    forget()
    yield install
    forget()


def test_two_one_slot_instances_behind_a_balancer_serve_two_requests_at_once(network):
    network(_balancer())

    profile = REAL_READ(BASE)

    assert profile.slots == 2
    assert (profile.endpoints, profile.slot_context, profile.quantisation) == (2, 231168, "Q4_K_M")


def test_two_two_slot_instances_serve_four(network):
    network(_balancer(first=_props(slots=2), second=_props(slots=2)))

    assert REAL_READ(BASE).slots == 4


def test_a_request_may_use_only_the_smallest_slot_context_in_the_pool(network):
    network(_balancer(second=_props(n_ctx=65536)))

    assert REAL_READ(BASE).slot_context == 65536


@pytest.mark.parametrize("status", ["offline", "unhealthy", "unknown"])
def test_an_endpoint_that_takes_no_requests_counts_nothing(network, status):
    network(_balancer(status=_status("healthy", status)))

    profile = REAL_READ(BASE)

    assert (profile.slots, profile.endpoints) == (1, 1)


def test_an_endpoint_serving_another_model_counts_nothing(network):
    other = _props(slots=4, alias="other-model", path="/models/Other-Model-Q8_0.gguf")
    network(_balancer(second=other))

    profile = REAL_READ(BASE, "", MODEL)

    assert (profile.slots, profile.endpoints) == (1, 1)


def test_an_endpoint_that_does_not_answer_counts_nothing(network):
    answers = _balancer()
    del answers["http://host.docker.internal:2002/props"]
    network(answers)

    assert REAL_READ(BASE).slots == 1


def test_the_balancer_s_endpoints_on_its_own_machine_are_reached_through_its_address(network):
    """Olla lists them at 127.0.0.1, which from the harness's container is the container itself."""
    net = network(_balancer())

    REAL_READ(BASE, "sk-balancer")

    asked = [url for url, _ in net.asked]
    assert "http://host.docker.internal:2001/props" in asked
    assert "http://host.docker.internal:2002/props" in asked
    assert not any("127.0.0.1" in url for url in asked)


def test_the_balancer_s_key_is_not_sent_to_an_endpoint_on_another_machine(network):
    status = _status()
    status["endpoints"][1]["url"] = "http://gpu-box:2002"
    answers = _balancer(status=status)
    answers["http://gpu-box:2002/props"] = answers.pop("http://host.docker.internal:2002/props")
    net = network(answers)

    profile = REAL_READ(BASE, "sk-balancer", MODEL)

    sent = {url: headers for url, headers in net.asked}
    assert profile.slots == 2
    assert "Authorization" not in sent["http://gpu-box:2002/props"]
    assert sent["http://host.docker.internal:2001/props"]["Authorization"] == "Bearer sk-balancer"


def test_a_single_server_is_read_as_before_and_its_missing_status_page_asked_once(network):
    single = "http://host.docker.internal:8888"
    net = network({single + "/props": _props(slots=4), single + "/internal/status/endpoints": 404})

    profiles = [REAL_READ(single + "/v1") for _ in range(3)]

    assert {(p.slots, p.endpoints) for p in profiles} == {(4, None)}
    assert sum(url.endswith("/internal/status/endpoints") for url, _ in net.asked) == 1


def test_a_server_down_at_its_first_read_is_read_once_it_is_back(network):
    """A server that did not answer was remembered as one without `/props`, and never read again in that process."""
    single = "http://host.docker.internal:8888"
    network({})
    assert REAL_READ(single + "/v1") is None

    network({single + "/props": _props(slots=4)})

    assert REAL_READ(single + "/v1").slots == 4


def test_the_worker_records_the_pool_for_the_configured_model(network, monkeypatch):
    network(_balancer(second=_props(slots=4, alias="other-model", path="/models/Other-Q8_0.gguf")))
    monkeypatch.setattr(server_profile, "read", REAL_READ)
    monkeypatch.setattr("app.models._runtime_settings", lambda: SimpleNamespace(
        openai_base_url=BASE, openai_api_key="", model_name=MODEL, llm_provider="local"))

    try:
        recorded = server_profile.record()
    finally:
        server_profile.forget()

    assert (recorded.slots, recorded.endpoints) == (1, 1)


def _server_facts():
    source = (ROOT / "scripts" / "loop" / "model_ready.py").read_text()
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "server_facts")
    scope: dict = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "model_ready", "exec"), scope)
    return scope["server_facts"]


def test_readiness_names_the_endpoints_and_their_total_slots(network, monkeypatch):
    network(_balancer())
    monkeypatch.setattr(server_profile, "read", REAL_READ)

    said = _server_facts()(BASE.rstrip("/"), {}, "", MODEL)

    assert "2 slot(s) across 2 endpoint(s)" in said
    assert "wait their turn" not in said
