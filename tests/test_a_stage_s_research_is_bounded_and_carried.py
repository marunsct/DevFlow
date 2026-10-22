"""A stage's documentation and registry lookups: a share per visit, batched, and carried to a fresh attempt.

Measured on one run's specification stage: 59 documentation reads and 30
registry lookups over four attempts, each attempt looking everything up again,
and each turn deciding on the next lookup 2-5 minutes of a frontier model
reasoning.
"""

from __future__ import annotations

import re

import pytest

from app.agents import stage_memory
from app.agents.carry_over import carry_over_note
from app.tools import docs, package_registry, research

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    stage_memory.forget_everything()
    monkeypatch.setattr(docs, "enabled", lambda: True)
    monkeypatch.setattr(docs, "read", lambda name, topic, ecosystem="": {"source": ["s"], "excerpt": f"{name} {topic}"})
    monkeypatch.setattr(package_registry, "look_up", lambda ecosystem, name: {"package": name, "version": "1.0.0"})
    yield
    stage_memory.forget_everything()


def test_a_stage_visit_has_a_share_of_documentation_reads():
    read_docs = docs.build_docs_tool()

    with stage_memory.remembering("stage-visit-1"):
        answers = [read_docs.invoke({"name": "hono", "topic": f"t{n}"}) for n in range(research.MOST_DOCUMENTATION_READS + 1)]
    with stage_memory.remembering("stage-visit-2"):
        fresh = read_docs.invoke({"name": "hono", "topic": "t"})

    assert all("excerpt" in answer for answer in answers[:-1])
    assert "Write your answer from what you have found" in answers[-1]["error"]
    assert not BANNED.search(answers[-1]["error"])
    assert "excerpt" in fresh, "another visit has its own share"


def test_several_packages_are_looked_up_in_one_call_and_each_counts():
    look_up_package = package_registry.build_package_lookup_tool()

    with stage_memory.remembering("stage-visit"):
        both = look_up_package.invoke({"ecosystem": "npm", "name": "hono, @hono/node-server"})
        one = look_up_package.invoke({"ecosystem": "npm", "name": "typescript"})
        over = look_up_package.invoke({"ecosystem": "npm", "name": ", ".join(f"p{n}" for n in range(research.MOST_PACKAGE_LOOKUPS))})

    assert [p["package"] for p in both["packages"]] == ["hono", "@hono/node-server"]
    assert one["package"] == "typescript"
    assert "share of packages lookups" in over["error"]


def test_a_fresh_attempt_is_handed_what_the_last_one_looked_up():
    with stage_memory.remembering("thread-a"):
        docs.build_docs_tool().invoke({"name": "hono", "topic": "serve options"})
        package_registry.build_package_lookup_tool().invoke({"ecosystem": "npm", "name": "hono"})

    note = carry_over_note("thread-a", None)

    assert "read_docs hono: serve options -> hono serve options" in note
    assert "look_up_package npm hono -> package: hono, version: 1.0.0" in note


def test_a_lookup_the_stage_has_used_its_share_of_is_no_longer_offered():
    """Told it had had its share, a specification stage asked again eight times, a frontier turn each."""
    from types import SimpleNamespace

    from app.agents.stage_memory import remembering
    from app.tools import research

    class _Request(SimpleNamespace):
        def override(self, **changes):
            return _Request(**{**self.__dict__, **changes})

    tools = [SimpleNamespace(name="read_docs"), SimpleNamespace(name="look_up_package"), {"name": "read_file"}]
    middleware = research.build_research_share_middleware()
    offered = []

    with remembering("thread-share"):
        middleware.wrap_model_call(_Request(tools=tools), lambda r: offered.append([research._named(t) for t in r.tools]))
        for _ in range(research.MOST_DOCUMENTATION_READS):
            assert research.over_its_share("documentation") is None
        middleware.wrap_model_call(_Request(tools=tools), lambda r: offered.append([research._named(t) for t in r.tools]))

    assert offered == [["read_docs", "look_up_package", "read_file"], ["look_up_package", "read_file"]]


def test_every_role_agent_has_it_outside_gathering():
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent.create_role_agent)
    assert source.index("build_research_share_middleware()") < source.index("*_gathering(model, response_format)")
