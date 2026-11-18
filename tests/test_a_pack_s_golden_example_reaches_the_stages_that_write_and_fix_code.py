"""The stages that write and fix code are shown the pack's golden example, on the versions the project pins.

Deep review 2026-11-18, item E4: on a new stack the model's traps were version skew - it remembered an older API than
the one pinned (axum's `Router<AppState>` and a `test` module that does not exist, Slim's `getErrorMiddleware`, .NET's
`Results.StatusCode(int, obj)`) - and the scaffold showed only a health route, so the first thing a stage had to
invent was the trap. The known causes were added only at triage, a failed round later.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.agents.specialists import project_contract
from app.graph.drafting import draft_request
from app.stacks import contract
from app.stacks.packs import ALL_PACKS
from app.stacks.packs.rust_axum_api import PACK as RUST

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rust_project(tmp_path):
    contract.write(tmp_path, RUST, "notes", "Notes", package="notes")
    return tmp_path


def _drafted(root, path: str) -> str:
    work = SimpleNamespace(acceptance_criteria=[], task_description="Add the notes endpoints.", interfaces=[], files=[path])
    return draft_request(root, path, work, None, SimpleNamespace(language="Rust", framework="axum"))


def test_the_contract_every_builder_and_fixer_reads_shows_the_example_on_the_pinned_version(tmp_path):
    text = project_contract(str(_rust_project(tmp_path)))

    assert contract.REFERENCE_CODE_HEADING in text
    assert ".with_state(state)" in text and '"/items/{id}"' in text, "axum 0.8's state and path syntax"
    assert "notes::app()" in text and "{{package}}" not in text, "the project's own crate name is filled in"


def test_a_stage_that_only_plans_is_not_given_the_example(tmp_path):
    text = project_contract(str(_rust_project(tmp_path)), with_reference_code=False)

    assert text and contract.REFERENCE_CODE_HEADING not in text


def test_drafting_a_file_in_the_example_s_language_shows_it_and_a_document_does_not(tmp_path):
    root = _rust_project(tmp_path)

    assert contract.REFERENCE_CODE_HEADING in _drafted(root, "notes/src/routes.rs")
    assert contract.REFERENCE_CODE_HEADING not in _drafted(root, "notes/README.md")


def test_a_rewrite_fixer_is_shown_the_example_too(tmp_path):
    from app.graph.rewritten_fixes import fix_request

    root = _rust_project(tmp_path)
    (root / "notes" / "src").mkdir(parents=True)
    (root / "notes" / "src" / "lib.rs").write_text("pub fn app() -> axum::Router { axum::Router::new() }\n")
    defect = SimpleNamespace(description="the build fails", expected_behavior="it builds", actual_behavior="")

    text = fix_request(root, "notes/src/lib.rs", defect, "error[E0432]", None,
                       SimpleNamespace(language="Rust", framework="axum"), [], [])

    assert contract.REFERENCE_CODE_HEADING in text


def test_a_workspace_on_a_pack_with_no_example_is_given_none(tmp_path):
    pack = next(p for p in ALL_PACKS if not p.golden_example)
    contract.write(tmp_path, pack, "app", "App")

    assert contract.reference_code(tmp_path) == ""


@pytest.mark.parametrize("pack", [p for p in ALL_PACKS if p.golden_example], ids=lambda p: p.name)
def test_the_reference_code_is_bounded_and_says_none_of_the_banned_words(tmp_path, pack):
    contract.write(tmp_path, pack, "product", "Product", package="product")

    text = contract.reference_code(tmp_path)

    assert contract.REFERENCE_CODE_HEADING in text
    assert len(text) <= contract.MOST_REFERENCE_CHARACTERS + len(contract.REFERENCE_CODE_HEADING) \
        + len(contract.REFERENCE_CODE_NOTE) + 200
    assert not BANNED.findall(text)


@pytest.mark.parametrize("pack", [p for p in ALL_PACKS if p.golden_example], ids=lambda p: p.name)
def test_a_golden_example_keeps_what_the_pack_holds_its_entry_to_and_carries_a_unit_test(pack):
    """The example replaces the scaffold's entry, so what the pack holds that entry to must still hold of the files it
    replaces, and its own unit test sits where the pack's unit command finds it."""
    files = pack.filled_files(pack.golden_example, "product", "Product", "product")
    unit_glob = re.compile(re.escape(pack.unit_pattern).replace(r"\*", "[^/]*") + "$")

    for path, held in ((p, h) for p, h in pack.required_signatures.items() if p in files):
        for pattern, _ in held:
            assert re.search(pattern, files.get(path, ""), re.M), f"{pack.name}: {path} no longer matches {pattern}"
    assert any(unit_glob.search(path.rsplit("/", 1)[-1]) and path.startswith(pack.unit_dir.strip("./"))
               for path in files), f"{pack.name}: no unit test in {pack.unit_dir}"
    assert pack.entrypoint in {*files, ""}, f"{pack.name}: the example does not show the entry it replaces"
