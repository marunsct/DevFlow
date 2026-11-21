"""A Go stack whose framework field says `net/http` on its own or with `(stdlib)` chooses the Go pack.

Measured on one Go run: the selector wrote "net/http (stdlib)"; split on its slash the field left a word `net` that no
pack implements, so no pack fitted, the run was set up by hand (a custom stack with no start script of the pack's and a
suite author that could not find `go` in its own sandbox) and an hour went on the suite stage.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.stacks import choose_pack


def _go(framework: str):
    return SimpleNamespace(language="Go", framework=framework, frontend_framework="", database="SQLite",
                           testing_framework="go test", additional_tools=[], product_kind="http_api")


def test_net_http_with_stdlib_chooses_the_go_pack():
    assert choose_pack(_go("net/http (stdlib)"), "a notes api").name == "go-http-api"


def test_net_http_alone_chooses_the_go_pack():
    assert choose_pack(_go("net/http"), "a notes api").name == "go-http-api"


def test_a_framework_the_pack_does_not_implement_still_chooses_none():
    assert choose_pack(_go("chi"), "a notes api") is None
