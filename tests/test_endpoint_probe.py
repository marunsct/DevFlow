"""A model server that is not there must not look like one that is slow.

Measured on one run: Docker Desktop wedged, the worker died, and the run
sat at `awaiting_approval:principal_architect` reporting `running` for about
ten hours. Nothing in the pipeline ever asked whether the endpoint answered.

The probe is deliberately biased towards "reachable". Blocking a run that would
have worked is worse than the stall it prevents, so every ambiguous answer -
an auth challenge, a missing route, a probe that cannot run at all - counts as
serving. Only a transport failure counts as absent.

That bias is not theoretical. While diagnosing this run I assumed a configured
endpoint was dead without testing it, and changed a correct setting to a
fragile one. The endpoint was unsloth studio's front end on :8888, which
answers 401 without a key and 200 with one. A probe that treated 401 as "not
there" would have made that mistake automatic and permanent.
"""

from __future__ import annotations

import urllib.error

import pytest

from app.models.endpoint_probe import EndpointStatus, probe_endpoint


def test_no_base_url_is_not_a_failure():
    """A hosted provider has nothing local to check."""
    status = probe_endpoint("")

    assert status.reachable
    assert "nothing local to check" in status.detail


def test_a_dead_port_is_reported_with_what_to_do(tmp_path):
    # Port 1 is privileged and never a model server.
    status = probe_endpoint("http://127.0.0.1:1/v1", timeout=2)

    assert not status.reachable
    assert "127.0.0.1:1" in status.detail
    assert "different port" in status.detail


def test_an_auth_challenge_counts_as_serving(monkeypatch):
    """401 means a server is there and wants a key - the run should start.

    This is the case that matters most: unsloth studio's endpoint answers 401
    without a key and 200 with the configured one.
    """
    def _raise_401(*args, **kwargs):
        raise urllib.error.HTTPError("http://x/v1/models", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("app.models.endpoint_probe._listening", lambda *a: True)
    monkeypatch.setattr("urllib.request.urlopen", _raise_401)

    status = probe_endpoint("http://localhost:8888/v1")

    assert status.reachable
    assert "HTTP 401" in status.detail
    assert "it is running" in status.detail


@pytest.mark.parametrize("code", [403, 404, 405, 500])
def test_any_http_answer_counts_as_serving(monkeypatch, code):
    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError("http://x/v1/models", code, "", {}, None)

    monkeypatch.setattr("app.models.endpoint_probe._listening", lambda *a: True)
    monkeypatch.setattr("urllib.request.urlopen", _raise)

    assert probe_endpoint("http://localhost:8888/v1").reachable


def test_a_transport_failure_is_the_only_absence(monkeypatch):
    monkeypatch.setattr("app.models.endpoint_probe._listening", lambda *a: True)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("connection refused")),
    )

    status = probe_endpoint("http://localhost:8888/v1")

    assert not status.reachable
    assert "connection refused" in status.detail


def test_the_docker_host_alias_is_not_judged_by_a_socket_check(monkeypatch):
    """`host.docker.internal` resolves only inside a container.

    Outside one the name fails, which says nothing about the server, so the
    HTTP request must decide instead of the socket probe.
    """
    calls = []
    monkeypatch.setattr(
        "app.models.endpoint_probe._listening",
        lambda *a: calls.append(a) or False,
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.HTTPError("http://x", 401, "", {}, None)
        ),
    )

    status = probe_endpoint("http://host.docker.internal:8888/v1")

    assert status.reachable, "a failed socket check must not condemn the docker alias"


def test_a_probe_that_cannot_run_does_not_block(monkeypatch):
    from app.models.endpoint_probe import describe_model_endpoint

    class _Explodes:
        @property
        def openai_base_url(self):
            raise RuntimeError("settings unreadable")

    status = describe_model_endpoint(_Explodes())

    assert status.reachable
    assert "not blocking" in status.detail


def test_status_is_truthy_when_reachable():
    assert bool(EndpointStatus(True, "ok"))
    assert not bool(EndpointStatus(False, "gone"))


def test_an_unresolvable_docker_alias_does_not_condemn_the_server():
    """`host.docker.internal` is provided by the container runtime.

    Outside a container the name does not resolve, which says nothing about the
    server. Reading that as absence refuses every run started from a host shell
    - which is exactly what happened when this probe was first wired in: 13
    tests failed with "No model server answered at
    http://host.docker.internal:1234/v1/models (Temporary failure in name
    resolution)".
    """
    status = probe_endpoint("http://host.docker.internal:1234/v1", timeout=3)

    assert status.reachable
    assert "not in a container" in status.detail


def test_a_refused_connection_is_still_absence():
    """The alias exemption is for DNS only, not for a server that is down."""
    status = probe_endpoint("http://127.0.0.1:1/v1", timeout=2)

    assert not status.reachable
    assert "Nothing is listening" in status.detail


@pytest.mark.parametrize(
    "message",
    ["Temporary failure in name resolution", "Name or service not known", "nodename nor servname"],
)
def test_every_dns_phrasing_is_recognised(message):
    from app.models.endpoint_probe import _is_name_resolution_failure

    assert _is_name_resolution_failure(urllib.error.URLError(message))


def test_a_refused_connection_is_not_read_as_dns():
    from app.models.endpoint_probe import _is_name_resolution_failure

    assert not _is_name_resolution_failure(urllib.error.URLError("Connection refused"))


# ---------------------------------------------------------------------------
# A server with no model loaded answers `/models` with 200 and `{"data": []}`,
# so every check that asks "is anything serving here" passes, and the run dies
# on its first model call instead.
#
# Measured on one run: LM Studio unloaded its model thirty-five minutes
# in, and the next call returned `400 - No models loaded`. The harness
# reported that well; what it could not do was refuse to start, because the
# probe had already called the endpoint healthy.
# ---------------------------------------------------------------------------


def _serving(monkeypatch, body: str, *, status: int = 200):
    """Point the probe at a fake server returning `body`."""
    import io
    import urllib.request

    from app.models import endpoint_probe

    monkeypatch.setattr(endpoint_probe, "_listening", lambda *a, **k: True)

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **k: _Response(body.encode())
    )


def test_a_server_with_no_model_loaded_is_not_ready(monkeypatch):
    from app.models.endpoint_probe import probe_endpoint

    _serving(monkeypatch, '{"data": [], "object": "list"}')

    status = probe_endpoint("http://localhost:1234/v1")

    assert not status.reachable
    assert "no model loaded" in status.detail
    assert "lms load" in status.detail, "the message must name the remedy"


def test_a_server_with_a_model_loaded_is_ready(monkeypatch):
    from app.models.endpoint_probe import probe_endpoint

    _serving(monkeypatch, '{"data": [{"id": "openai/gpt-oss-20b"}], "object": "list"}')

    status = probe_endpoint("http://localhost:1234/v1")

    assert status.reachable
    assert "gpt-oss-20b" in status.detail


def test_a_server_that_does_not_publish_its_models_is_left_alone(monkeypatch):
    """"Cannot tell" must never become "not there"."""
    from app.models.endpoint_probe import probe_endpoint

    for body in ('{"ok": true}', "not json at all", "[]"):
        _serving(monkeypatch, body)
        assert probe_endpoint("http://localhost:1234/v1").reachable, body


def test_the_models_key_is_read_under_either_name(monkeypatch):
    from app.models.endpoint_probe import probe_endpoint

    _serving(monkeypatch, '{"models": []}')
    assert not probe_endpoint("http://localhost:1234/v1").reachable

    _serving(monkeypatch, '{"models": [{"name": "llama"}]}')
    assert probe_endpoint("http://localhost:1234/v1").reachable
