"""No stage's system prompt, rendered as the stage is built, carries a product word.

The rule bans the whole words task, tasks, to-do, todo, button, click and checkbox in each new prompt rule, and each
new rule has its own test. Nothing scanned the prompts as rendered, so older shared text kept them: the per-role audit
of 2026-11-20 counted 46 hits in 13 of 28 rendered prompts ("a task dashboard" in six roles, twelve in the technical
lead's). A small model reads a product word in a rule as a hint about the product it is building.

Every role agent is built here, the acceptance suite's writer included, in an empty workspace and in workspaces
scaffolded from a page, a service and a command-line pack, and the system prompt each is built with is scanned, with
the environment contract every stage's prompt is sent with.
"""

from __future__ import annotations

import json
import re

import pytest

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: A page, a service and a command-line stack: the scaffold changes the layout section each prompt is built with.
PACKS = ("browser-javascript", "csharp-aspnet-api", "python-cli")
#: Text another change is rewording (the environment contract's description of the browser), cut before the scan.
#: Remove an entry once its text no longer carries the word; nothing else may be added here.
def _render(root) -> dict[str, str]:
    """{agent name: the system prompt it is built with}, for every role agent built in `root`."""
    from deepagents import create_deep_agent

    import app.agents.role_agent as role_agent
    from app.agents.specialists import create_specialist_agent
    from app.models import CompatibleChatOpenAI
    from tests.test_prompt_names_only_offered_tools import _builders

    model = CompatibleChatOpenAI(model="Qwen3.5-9B-GGUF", api_key="unused", base_url="http://localhost:9/v1")
    captured: dict[str, str] = {}

    def spy(**kwargs):
        name = kwargs["name"]
        captured[f"{name} (suite)" if name in captured else name] = kwargs["system_prompt"]
        return create_deep_agent(**kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(role_agent, "create_deep_agent", spy)
        for build in _builders():
            build(model=model, repo_root=root)
        create_specialist_agent("testing", model=model, repo_root=root, writing_the_suite=True)
    return captured


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict[str, str]:
    """{"<workspace>: <agent>": prompt} for an empty workspace and one per pack, and the environment contract."""
    from app.agents.environment_contract import environment_contract_text

    prompts = {f"empty: {name}": text for name, text in _render(tmp_path_factory.mktemp("empty")).items()}
    for pack in PACKS:
        root = tmp_path_factory.mktemp(pack)
        (root / ".harness").mkdir()
        (root / ".harness" / "stack-pack.json").write_text(json.dumps({
            "pack": pack, "project": "ledger", "title": "Ledger", "package": "ledger", "acceptance_dir": "acceptance",
        }))
        prompts.update({f"{pack}: {name}": text for name, text in _render(root).items()})
    prompts["environment contract"] = environment_contract_text()
    return prompts


def test_every_stage_and_every_workspace_is_rendered(rendered):
    assert len(rendered) >= 4 * 16
    assert "python-cli: specialist_testing (suite)" in rendered


def test_no_rendered_system_prompt_carries_a_product_word(rendered):
    def hits(prompt: str) -> list[str]:
        return [" ".join(prompt[max(0, m.start() - 40):m.end() + 20].split()) for m in BANNED.finditer(prompt)]

    assert {name: found for name, prompt in rendered.items() if (found := hits(prompt))} == {}
