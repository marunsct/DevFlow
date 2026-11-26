"""Every language a pack is written in has one full row saying what each mechanism knows of it.

Deep review 2026-11-18, item E3: about twenty mechanisms each covered only some languages (the test totals read from
a runner's output, the image a command runs in, the runtime pinned, the registry docs come from) and twelve lists of
"folders that are not the product's code" each differed; each gap was found one run at a time. The language table
says it once per language, and a field with no answer is a `Gap` with its reason - never left out.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from app.analysis import parsed_definitions
from app.analysis.compiler_check import CHECKERS
from app.analysis.import_resolvers import RESOLVERS
from app.analysis.reachability import FAMILIES
from app.analysis.resolved_packages import READERS as RESOLVED_READERS
from app.plugins.seed import DEVELOPMENT_SERVERS
from app.stacks.languages import Gap, LanguageSupport, image_of, language
from app.stacks.packs import ALL_PACKS
from app.tools.runtimes import SUPPORTED
from app.tools.sandbox import RUNNERS_COUNTED

PACK_LANGUAGES = sorted({pack.language for pack in ALL_PACKS})
#: What a "check" names besides a compiler checker: the two language services of `app.analysis.language_service`.
LANGUAGE_SERVICES = {"language_service", "pyright"}


@pytest.mark.parametrize("name", PACK_LANGUAGES)
def test_every_field_of_a_pack_language_s_row_is_answered_or_a_gap_with_its_reason(name):
    row = language(name)

    assert isinstance(row, LanguageSupport), f"no row for {name}, which a pack is written in"
    for each in fields(LanguageSupport):
        value = getattr(row, each.name)
        if isinstance(value, Gap):
            assert value.reason.strip(), f"{name}.{each.name} is a gap with no reason"
        elif each.name not in {"installed", "installed_beside", "build_output_beside", "build_output_by_name"}:
            assert value, f"{name}.{each.name} is empty"


@pytest.mark.parametrize("name", PACK_LANGUAGES)
def test_what_a_row_names_is_a_mechanism_that_exists(name):
    row = language(name)

    if not isinstance(row.check, Gap):
        assert row.check in {checker.language for checker in CHECKERS} | LANGUAGE_SERVICES
    if not isinstance(row.test_totals, Gap):
        assert set(row.test_totals) <= set(RUNNERS_COUNTED), f"{name}'s runners are not all counted"
    if not isinstance(row.runtime_version, Gap):
        assert row.runtime_version in SUPPORTED
    if not isinstance(row.import_graph, Gap):
        assert row.import_graph in FAMILIES
    if not isinstance(row.development_server, Gap):
        assert row.development_server in DEVELOPMENT_SERVERS
    if not isinstance(row.resolved, Gap):
        assert row.resolved in RESOLVED_READERS
    if not isinstance(row.tree, Gap):
        assert row.tree.resolver in RESOLVERS or (not row.tree.resolver and not isinstance(row.import_graph, Gap))
        # Every pattern fits its grammar: one that does not leaves the language to the line patterns, unseen.
        assert all(parsed_definitions.loads(f"a{suffix}") for suffix in row.tree.grammars), f"{name}'s tree reading"


@pytest.mark.parametrize("name", PACK_LANGUAGES)
def test_a_row_s_image_is_the_one_its_programs_and_services_run_in(name):
    """A fullstack pack runs its page's toolchain beside the service's, so only single-toolchain packs are compared."""
    images = {pack.sandbox_image for pack in ALL_PACKS
              if pack.language == name and pack.kind != "fullstack" and pack.sandbox_image}

    assert images == {image_of(language(name))}


def test_each_pack_s_unit_runner_is_one_its_language_s_row_counts():
    """The runner each pack's own unit command runs is read for totals: measured, Rust's nextest and Rails'
    minitest were counted by nothing."""
    runner_of = {"npm": None, "gotestsum": "gotestsum", "cargo": "nextest", "mvn": "maven", "dotnet": "dotnet",
                 "rspec": "rspec", "rails": "minitest", "phpunit": "phpunit", "pytest": "pytest"}
    for pack in ALL_PACKS:
        words = [part.rsplit("/", 1)[-1] for part in pack.unit_test]
        runner = next((runner_of[word] for word in words if word in runner_of and runner_of[word]), None)
        if runner is None:
            continue
        assert runner in language(pack.language).test_totals, f"{pack.name}: {runner}"
