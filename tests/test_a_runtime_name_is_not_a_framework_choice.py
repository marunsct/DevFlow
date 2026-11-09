"""A runtime a pack lists is not the stack choosing that pack's framework.

Measured on one run: the stack chose "Hono 4 served by @hono/node-server" and
was given the Node pack built on Express, because that pack lists "node" and
"node" was found inside "@hono/node-server". The stack record was rewritten to
Express against a brief that required Hono. Only a name of the pack's own
framework counts now, matched as a whole name; a scoped package counts as its
scope's framework.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.stacks import choose_pack


def _stack(language, framework, kind="http_api"):
    return SimpleNamespace(
        language=language, framework=framework, frontend_framework="",
        database="JSON file", testing_framework="node:test, Playwright", product_kind=kind,
    )


@pytest.mark.parametrize("framework", ["Elysia on Node", "Fastify on Node.js"])
def test_another_framework_on_the_same_runtime_gets_no_pack(framework):
    assert choose_pack(_stack("TypeScript on Node.js >= 20", framework), "") is None


@pytest.mark.parametrize("framework", [
    "Hono 4 served by @hono/node-server 2, bound to 127.0.0.1:$PORT",
    "Hono HTTP framework on Node.js",
])
def test_hono_on_node_is_hono_s_pack_and_not_express_s(framework):
    """The stack named Hono served by @hono/node-server: the Express pack must not take it, the Hono one does."""
    assert choose_pack(_stack("TypeScript on Node.js >= 20", framework), "").name == "node-hono-api"


@pytest.mark.parametrize("language, framework, chosen", [
    ("JavaScript", "Express 4 on Node.js", "node-http-api"),
    ("JavaScript", "Express.js", "node-http-api"),
    ("TypeScript", "@nestjs/core 10 on Node", "node-nest-api"),
    ("JavaScript", "Node.js built-in http module", "node-http-api"),
    ("Go", "Go standard library (net/http)", "go-http-api"),
    ("Go", "None (stdlib)", "go-http-api"),
    ("C#", "ASP.NET Core minimal API", "csharp-aspnet-api"),
    ("Java", "Spring Boot 3", "java-spring-api"),
    ("Ruby", "Ruby on Rails 7 (API mode)", "ruby-rails-api"),
])
def test_a_framework_named_in_any_form_still_gets_its_pack(language, framework, chosen):
    assert choose_pack(_stack(language, framework), "").name == chosen
