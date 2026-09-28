"""No agent is told where the workspace is on the host.

Inside an agent every path resolves against a workspace rooted at "/". The
host path - `/app/data/workspaces/<label>-<run-id>` - names nothing the agent
can reach, so reading it answers `not found` and writing it builds a mirror of
the host layout inside the workspace, which is what one run actually did.

`product_manager` has carried that reasoning in a comment since one run
and was the only caller that acted on it. Five other briefs opened with
`Repository root: {repository_root}`, and the agents used it. Measured across
the stored run histories: 15 of 24 runs carry that string into tool calls.
One run completed cleanly and still spent six calls on it, five returning
`not found` or `path_not_found`; one run spent 432 calls and 254 approval
gates before dying of gate exhaustion.

This is a source-level property rather than six separate assertions, because
the failure mode here is a sixth caller being added later - the same shape as
finding 27, where a test written against the one symptom passed while the
defect sat in the stage nobody had converted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / "src" / "app" / "agents"

#: Interpolating any of these into text a MODEL reads hands over a host path.
HOST_PATH_FIELDS = re.compile(r"\{(?:repository_root|repo_root|[\w.]*\.source_path)\}")

#: Human-facing text, where the host path is the useful fact. `role_agent`
#: renders approval descriptions for a person deciding whether to allow a
#: deletion or a command, and "which workspace" is exactly what they need.
HUMAN_FACING = {"role_agent.py"}


@pytest.mark.parametrize(
    "module",
    sorted(p.name for p in AGENTS.glob("*.py") if p.name not in HUMAN_FACING),
)
def test_no_agent_brief_interpolates_a_host_path(module: str) -> None:
    source = (AGENTS / module).read_text(encoding="utf-8")

    offenders = [
        line.strip()
        for line in source.splitlines()
        if HOST_PATH_FIELDS.search(line) and not line.lstrip().startswith("#")
    ]

    assert not offenders, (
        f"{module} puts a host path into text a model reads: {offenders}. "
        "Use app.agents.project_layout.WORKSPACE_ROOT_NOTE instead - telling an "
        "agent the path and then telling it not to use the path does not work."
    )


def test_the_note_says_what_to_use_instead() -> None:
    from app.agents.project_layout import WORKSPACE_ROOT_NOTE

    assert "rooted at '/'" in WORKSPACE_ROOT_NOTE
    assert "/app/data" not in WORKSPACE_ROOT_NOTE


def test_every_brief_builder_that_takes_a_root_withholds_it() -> None:
    """The rendered output, not just the source - one assertion per builder."""
    from app.agents.architecture_reviewer import build_architecture_review_request
    from app.agents.security_reviewer import build_security_review_request
    from app.agents.technical_lead import build_milestone_planning_request

    root = "/app/data/workspaces/t18-run-a0000006"
    rendered = [
        build_architecture_review_request("spec", root),
        build_security_review_request(["a.js"], "none", root),
        build_milestone_planning_request("plan", "goal", root),
    ]

    for request in rendered:
        body = request["messages"][0]["content"]
        assert root not in body
        assert "rooted at '/'" in body


def test_no_brief_claims_a_completeness_it_does_not_have() -> None:
    """Several briefs quote a document through `_truncate`.

    Saying "quoted in full below" over truncated text tells an agent not to
    read the real file exactly when it should - the same defect as a document
    naming a file that does not exist, pointed the other way. The headers name
    the source path instead, which is true whether or not the text was cut.
    """
    import re

    offenders = []
    for module in AGENTS.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "quoted in full" in line and not line.lstrip().startswith("#"):
                offenders.append(f"{module.name}: {line.strip()}")

    assert not offenders, offenders


def test_a_quoted_document_names_the_file_it_came_from() -> None:
    """So an agent that wants the untruncated text knows where to look, instead
    of inventing `/home/user/workspace/docs/product_intake.md` - which
    one run's stack selector did five times."""
    from app.agents.stack_selector import build_stack_selector_request

    body = build_stack_selector_request("intake", "tools", _Repo())["messages"][0][
        "content"
    ]

    # ABSOLUTE, with the leading slash. Written as `docs/product_intake.md`,
    # one run's architecture_review prepended its own `/docs/` and asked
    # for `/docs/docs/technology_stack.md` six times. That spelling appears in
    # no run before this change shipped. An absolute workspace path is what the
    # read tools accept and is the one thing an agent cannot prefix.
    assert "(/docs/product_intake.md)" in body
    assert "(/docs/tools_and_models.md)" in body
    assert "docs/docs/" not in body


class _Repo:
    branch = "master"
    commit = "abc1234"
    root_path = "/app/data/workspaces/t21-run-1"
    files: list = []
