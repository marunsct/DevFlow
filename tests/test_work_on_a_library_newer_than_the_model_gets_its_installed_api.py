"""Builders and fixers working on a file that uses a library newer than the model get its installed API (HK.7, LF.1302).

Measured: models write a library's calls as their training data had them - success on API changes made after a
model's cutoff fell from 56% to 33% and the release's own documentation raised it to 48-58% (RustEvo2, GitChameleon
2.0) - and here builders imported names the installed package did not have and every rewrite guessed again. Behind
`API_CARDS_FOR_NEWER_RELEASES` (off until measured), a dependency whose installed release line began after the build
model's training data ends gets a short card - the names its installed files export, its changelog and migration notes
on them, and its documentation for that release (Context7 pinned to the version) - in the requests of the builders
and fixers whose files use it. Off, those requests are byte for byte as before and nothing is asked.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.tools import package_registry, release_fit

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CUTOFF = "2024-06"

REGISTRY = {
    # Line 6 began after the cutoff; the installed 6.1.0 is on it.
    "registry.npmjs.org/quickserve": {
        "versions": {"5.2.0": {}, "6.0.0": {}, "6.1.0": {}},
        "time": {"5.2.0": "2023-05-01T00:00:00Z", "6.0.0": "2025-03-01T00:00:00Z", "6.1.0": "2025-06-01T00:00:00Z"},
    },
    # A release after the cutoff, on a line that began long before it: nothing the model cannot know.
    "registry.npmjs.org/steadylib": {
        "versions": {"2.0.0": {}, "2.4.0": {}},
        "time": {"2.0.0": "2021-01-01T00:00:00Z", "2.4.0": "2025-01-01T00:00:00Z"},
    },
}

CONTEXT7_SEARCH = {"results": [{"id": "/acme/quickserve", "title": "quickserve", "versions": ["v5.2.0", "v6.1.0"]}]}
CONTEXT7_ANSWER = {
    "infoSnippets": [{"content": "Since 6.0 a server is made with createApp(options); createServer was removed."}],
    "codeSnippets": [{"codeTitle": "Start a server",
                      "codeList": [{"language": "ts", "code": "const app = createApp();\napp.listen(3000);"}]}],
}


class Context7:
    """Context7 stood in for at the network's edge (`lookups._get`), recording each address asked."""

    def __init__(self, search=CONTEXT7_SEARCH):
        self.search, self.asked = search, []

    def __call__(self, url, headers, body=None):
        self.asked.append(url)
        if "context7.com/api/v2/libs/search" in url:
            return 200, json.dumps(self.search), {}
        if "context7.com/api/v2/context" in url:
            return 200, json.dumps(CONTEXT7_ANSWER), {}
        return 404, "", {}

    def library_ids(self):
        return [parse_qs(urlsplit(u).query).get("libraryId", [""])[0] for u in self.asked if "/context?" in u]


@pytest.fixture
def newer_library(monkeypatch, tmp_path):
    """A project on quickserve 6.1.0 and steadylib 2.4.0, a model whose training data ends 2024-06, the registry and
    Context7 stood in for. Returns (workspace, Context7 spy)."""
    from app.models.model_guidance import served_now
    from app.models.registry import merge_into_fitness

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    monkeypatch.delenv("API_CARDS_FOR_NEWER_RELEASES", raising=False)
    for name in {served_now(), "default-model", "a-local-model"}:
        # As the model card's lookup keeps it (`capabilities.fill`).
        merge_into_fitness(name, {"capabilities_found": {"knowledge_cutoff": {"value": CUTOFF, "source": "model card"}}})
    for cache in (package_registry._CACHE, release_fit._CACHE):  # noqa: SLF001
        cache.clear()

    def registry(url, *_a, **_k):
        for tail, body in REGISTRY.items():
            if url.endswith(tail):
                return 200, json.dumps(body).encode()
        return 404, b""

    monkeypatch.setattr(package_registry, "_fetch", registry)
    spy = Context7()
    from app.tools import lookups

    monkeypatch.setattr(lookups, "_get", spy)

    root = tmp_path / "workspace"
    (root / ".harness").mkdir(parents=True)
    (root / ".harness" / "stack-facts.json").write_text(json.dumps({"dependencies": [
        {"ecosystem": "npm", "package": "quickserve", "version": "6.1.0", "newest": "6.1.0", "resolved": "6.1.0"},
        {"ecosystem": "npm", "package": "steadylib", "version": "2.4.0", "newest": "2.4.0"},
    ]}))
    package = root / "node_modules" / "quickserve"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "quickserve", "version": "6.1.0", "types": "index.d.ts"}))
    (package / "index.d.ts").write_text("export declare function createApp(options?: object): App;\n"
                                        "export declare function useLogger(): void;\nexport interface App {}\n")
    (package / "CHANGELOG.md").write_text("## 6.0.0\n- `createApp` replaces `createServer`.\n## 5.2.0\n- fixes\n")
    (package / "MIGRATION.md").write_text("# Migrating\n## From 5 to 6\nCall `createApp` where `createServer` was.\n"
                                          "## From 4 to 5\nOlder notes.\n")
    (root / "src").mkdir()
    (root / "src" / "server.ts").write_text("import { createApp } from 'quickserve';\nimport steady from 'steadylib';\n")
    (root / "src" / "util.ts").write_text("import steady from 'steadylib';\nexport const two = 2;\n")
    yield root, spy
    for cache in (package_registry._CACHE, release_fit._CACHE):  # noqa: SLF001
        cache.clear()


def _a_work_order(*files):
    from app.agents.technical_lead import SpecialistTask

    return SpecialistTask(specialist_role="backend", title="The server", task_description="Write the server.",
                          files=list(files))


def _builder_request(root, *files):
    from app.agents.specialists import build_specialist_task_request

    order = _a_work_order(*files)
    return build_specialist_task_request(order.task_description, [], str(root), work_order=order)[
        "messages"][0]["content"]


def test_a_work_order_on_a_file_using_a_newer_library_is_given_its_installed_api(newer_library, monkeypatch):
    root, context7 = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")

    request = _builder_request(root, "src/server.ts")

    assert "newer than this model's training data" in request
    assert "`quickserve` 6.1.0" in request and "2025-03-01" in request and CUTOFF in request
    # The names the installed files export, the one this file uses first; its changelog and migration notes on it.
    assert "`createApp` - then:" in request and "`useLogger`" in request
    assert "`createApp` replaces `createServer`" in request
    assert "From 5 to 6" in request and "Older notes" not in request
    # Its documentation for the installed release, Context7 asked with the version in the library id.
    assert context7.library_ids() == ["/acme/quickserve/v6.1.0"]
    assert "```ts\nconst app = createApp();\napp.listen(3000);\n```" in request
    # A library whose release line the model has seen gets no card.
    assert "`steadylib`" not in request


def test_a_work_order_whose_files_use_no_newer_library_gets_nothing(newer_library, monkeypatch):
    root, context7 = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")

    request = _builder_request(root, "src/util.ts")

    assert "newer than this model's training data" not in request
    assert context7.asked == []


def test_off_the_builder_s_request_is_as_before_byte_for_byte_and_nothing_is_asked(newer_library, monkeypatch, tmp_path):
    root, context7 = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "off")
    bare = tmp_path / "bare"
    (bare / "src").mkdir(parents=True)
    (bare / "src" / "server.ts").write_text((root / "src" / "server.ts").read_text())

    assert _builder_request(root, "src/server.ts") == _builder_request(bare, "src/server.ts").replace(str(bare), str(root))
    assert context7.asked == []
    assert not (root / ".harness" / "api-cards.json").exists()


def test_a_drafted_file_whose_entries_name_the_library_is_given_its_card(newer_library, monkeypatch):
    from app.graph import drafting

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")
    specification = SimpleNamespace(file_plan=["src/app.ts: the server, made with `quickserve`"])

    request = drafting.draft_request(root, "src/app.ts", SimpleNamespace(task_description="Write the server"),
                                     specification, None)

    assert "`quickserve` 6.1.0" in request


def test_a_fixer_of_a_file_using_a_newer_library_is_given_its_card(newer_library, monkeypatch):
    import the_fix_stage

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")
    defect = the_fix_stage.a_defect("The server does not start", affected_files=["src/server.ts"])

    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect))

    assert "`quickserve` 6.1.0" in seen.requests[0]
    assert "`createApp` - then:" in seen.requests[0]


def test_a_rewrite_of_a_file_using_a_newer_library_is_given_its_card(newer_library, monkeypatch):
    from app.graph import rewritten_fixes

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")
    defect = SimpleNamespace(description="It does not start", expected_behavior="starts", actual_behavior="crash",
                             affected_files=["src/server.ts"])

    request = rewritten_fixes.fix_request(root, "src/server.ts", defect, "TypeError: createServer is not a function",
                                          None, None, [], [], model=SimpleNamespace(model_name="a-local-model"))

    assert "`quickserve` 6.1.0" in request


def test_a_release_context7_does_not_list_is_never_asked_of_it(newer_library, monkeypatch):
    from app.tools import lookups, versioned_docs

    monkeypatch.setattr(lookups, "_get", spy := Context7({"results": [
        {"id": "/acme/quickserve", "title": "quickserve", "versions": ["v5.2.0"]}]}))

    found = versioned_docs.read("quickserve", "6.1.0", "quickserve 6 API", ecosystem="npm", newest="7.0.0")

    assert found == {}
    assert spy.library_ids() == []


@pytest.mark.parametrize("cutoff, flagged", [("2024-06", ["quickserve"]), ("2025-03", []), ("2025-02", ["quickserve"])])
def test_a_library_is_newer_than_the_model_when_its_installed_line_began_after_the_cutoff(newer_library, cutoff,
                                                                                         flagged):
    from app.stacks import api_cards

    root, _ = newer_library

    assert [entry["package"] for entry in api_cards.flagged(root, cutoff)] == flagged


def test_the_cards_stay_a_small_share_of_the_request_however_large_the_library(newer_library, monkeypatch):
    from app.stacks import api_cards

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")
    types = root / "node_modules" / "quickserve" / "index.d.ts"
    types.write_text("".join(f"export declare function call{n}(): void;\n" for n in range(500)))
    (root / "node_modules" / "quickserve" / "MIGRATION.md").write_text("## To 6\n" + "A long note.\n" * 5_000)

    section = api_cards.for_a_fixer(root, ["src/server.ts"], "", SimpleNamespace(model_name="a-local-model"))

    assert "`quickserve` 6.1.0" in section
    assert len(section) < 7_000


def test_a_card_whose_names_are_cut_does_not_call_the_rest_missing(newer_library, monkeypatch):
    """The card lists 40 names; past that, "A name not here is not exported by this release" was false."""
    from app.stacks import api_cards

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")
    (root / "node_modules" / "quickserve" / "index.d.ts").write_text(
        "export declare function createApp(): void;\n"
        + "".join(f"export declare function call{n:02d}(): void;\n" for n in range(59)))

    section = api_cards.for_a_fixer(root, ["src/server.ts"], "", SimpleNamespace(model_name="a-local-model"))

    assert "`createApp`" in section
    assert "is not exported by this release" not in section
    assert "20 more of its 60 names" in section and "may still be exported" in section


def test_a_card_with_every_name_listed_still_says_a_name_not_here_is_not_exported(newer_library, monkeypatch):
    from app.stacks import api_cards

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")

    section = api_cards.for_a_fixer(root, ["src/server.ts"], "", SimpleNamespace(model_name="a-local-model"))

    assert "A name not here is not exported by this release." in section


def test_the_cards_name_no_product_word(newer_library, monkeypatch):
    from app.stacks import api_cards

    root, _ = newer_library
    monkeypatch.setenv("API_CARDS_FOR_NEWER_RELEASES", "on")

    section = api_cards.for_a_fixer(root, ["src/server.ts"], "", SimpleNamespace(model_name="a-local-model"))

    assert section
    assert not BANNED.search(section.replace("createApp", "").replace("useLogger", ""))


@pytest.mark.parametrize("card, said", [
    ("Knowledge cutoff: June 2024.", "2024-06"),
    ("The pretraining data has a cutoff of December 2023.", "2023-12"),
    ("It was trained on data up to 2025-03.", "2025-03"),
])
def test_the_model_card_s_stated_cutoff_is_kept_with_the_model(card, said):
    from app.models.knowledge_cutoff import found_on_the_card

    assert found_on_the_card({"createdAt": "2026-01-10T00:00:00Z"}, card)["knowledge_cutoff"]["value"] == said


def test_a_card_that_states_none_gives_its_repository_s_creation_month_as_the_upper_bound():
    from app.models.knowledge_cutoff import found_on_the_card

    assert found_on_the_card({"createdAt": "2025-04-28T10:00:00Z"}, "A capable model.")["knowledge_cutoff"][
        "value"] == "2025-04"


def test_the_owner_s_cutoff_wins_over_the_card_s(monkeypatch, tmp_path):
    from app.models import capabilities, knowledge_cutoff
    from app.models.registry import merge_into_fitness

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    merge_into_fitness("m", {capabilities.FOUND_KEY: {"knowledge_cutoff": {"value": "2025-04", "source": "model card"}}})
    assert knowledge_cutoff.of("m") == "2025-04"

    capabilities.set_owner_values("m", {"knowledge_cutoff": "2024-10"})

    assert knowledge_cutoff.of("m") == "2024-10"
