"""No prompt may carry an example an agent can mistake for an instruction.

Every agent prompt is read by a model that has no way to know which nouns in it
are placeholders. A worked example naming a real product is therefore not an
example - it is a name, in an emphatic instruction, that the model will use.

Observed on run-0b55ad49: six prompts carried
`**CRITICAL INSTRUCTION**: ... a directory named after the app (e.g. `thehub/`
for 'The Hub')`. `thehub` is the product from an unrelated earlier run. Building
a to-do list application, an agent created `thehub/` at the workspace root and
put a third copy of the project in it - alongside `simple-todo-list-app/` and
`simple_todo_list_app/`. It followed the instruction exactly as written.
"""

from __future__ import annotations

import pathlib
import re

import pytest

AGENTS = sorted((pathlib.Path(__file__).resolve().parent.parent / "src/app/agents").glob("*.py"))

#: Names from products this repository has actually run, which must never appear
#: in a prompt. Add to this when a new one is used for testing.
PRODUCT_NAMES = ("thehub", "the hub", "simple-todo-list-app", "decision thread")


@pytest.mark.parametrize("module", AGENTS, ids=lambda p: p.name)
def test_no_prompt_names_a_product_from_another_run(module):
    text = module.read_text().lower()
    found = [name for name in PRODUCT_NAMES if name in text]

    assert not found, (
        f"{module.name} mentions {found}. A model cannot tell a placeholder from a "
        "name: an agent told to use `thehub/` created that directory while building "
        "something else entirely."
    )


@pytest.mark.parametrize("module", AGENTS, ids=lambda p: p.name)
def test_no_prompt_offers_a_path_as_an_example(module):
    """In a prompt, an `e.g.` path is not an example. It is a filename.

    Observed on run-0b55ad49: the shared prompt said "write document artifacts
    inside `docs/` (e.g., `docs/spec.md`)". An agent wrote a 1 KB `docs/spec.md`
    beside the real 51 KB `docs/technical_specification.md`; the milestone
    reviewer read the thin one and blocked the sprint for lacking detail that
    was in the other file all along. The same construct produced a `thehub/`
    directory in a run with nothing to do with The Hub.

    The rule is absolute rather than a list of acceptable examples, because
    deciding which examples are safe is the judgement that failed. Where a path
    is genuinely required, state it as an instruction - "write it to
    `docs/technical_specification.md`" - which is what it always meant.
    """
    paths = [
        found
        for found in re.findall(r"e\.g\.,?\s*`([^`]+)`", module.read_text())
        if "/" in found or found.endswith((".md", ".js", ".py", ".json", ".txt"))
    ]

    assert not paths, (
        f"{module.name} offers {paths} as an example path. State it as an "
        "instruction instead - a model cannot tell an example from a filename."
    )


def test_the_stack_selector_treats_a_stated_constraint_as_binding():
    """It had the constraint and selected past it anyway.

    On run-95ca3f72 the product intake said "single-page application using only
    HTML/CSS/JavaScript" and "code size capped at 500 lines". The stack
    selector chose Jest and Cypress - 1.8 GB of binaries downloaded into the
    run workspace. Configuring them consumed the sprint and all three of its
    remediation attempts, and the application was never started.

    The intake was faithful; nothing told the selector a constraint bounds the
    choice rather than colouring it.
    """
    from app.agents.stack_selector import _SYSTEM_PROMPT

    lowered = _SYSTEM_PROMPT.lower()

    assert "boundary, not a preference" in lowered
    assert "size the stack to the product" in lowered
    assert "may not select something" in lowered


#: A run identifier as this harness writes them: `run-` and a hex prefix.
RUN_IDENTIFIER = re.compile(r"run-[0-9a-f]{6,}")


def _prompt_strings():
    """Every string an agent module exposes as a value, with where it came from.

    A module docstring is excluded, and nothing else is. The docstrings in this
    repository are its evidence log - which run showed a rule was needed, and
    what it cost - and that record is for whoever changes the rule next. It is
    never sent anywhere. A string bound to a name can be, and several are
    re-exported through three modules before reaching a system prompt, so the
    check is on the value rather than on the file it is written in.
    """
    import importlib
    import pkgutil

    import app

    for module in pkgutil.walk_packages(app.__path__, "app."):
        try:
            loaded = importlib.import_module(module.name)
        except Exception:  # noqa: BLE001 - a module that will not import is another test's problem
            continue
        for attribute in dir(loaded):
            if attribute == "__doc__":
                continue
            try:
                value = getattr(loaded, attribute)
            except Exception:  # noqa: BLE001 - a property that raises is not a prompt
                continue
            if isinstance(value, str):
                yield f"{module.name}.{attribute}", value


def test_no_prompt_cites_a_run_identifier():
    """`run-519a9d8a` means nothing to the model reading it.

    The rules in these prompts were each written against a run that went wrong,
    and the citation went into the prompt beside the rule. It cannot be looked
    up from inside a run, it is not evidence to an agent the way it is to a
    reader of this repository, and it spends context on a token the model can
    only ignore.

    It also drags the run's technology in with it. A citation is always a
    citation of one particular product in one particular language, and the
    sentence around it names that product's files - so a rule that should hold
    for any stack arrives sounding like a rule about the last JavaScript app
    this harness built. The evidence belongs in the docstring, where it is
    already kept; the prompt keeps the observation without the identifier.
    """
    cited = {
        name: sorted(set(RUN_IDENTIFIER.findall(value)))
        for name, value in _prompt_strings()
        if RUN_IDENTIFIER.search(value)
    }

    assert not cited, (
        "these strings cite run identifiers: "
        + "; ".join(f"{name} {ids}" for name, ids in sorted(cited.items()))
        + ". Keep the observation, drop the identifier - it is unlookupable "
        "from inside a run and ties a general rule to one run's stack."
    )
