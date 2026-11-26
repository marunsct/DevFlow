"""`module_exports` never reads a cut list as the whole one, and can answer for one name.

Measured on a live fixer: asked twice for `pydantic`, the tool answered 60 names, `AfterValidator` to `NegativeInt`,
with "Only these names exist". The sort puts capitals first, so `ValidationError`, `field_validator` and every name
after them were left out and called missing; the defect was a test expecting `ValidationError`, and the product file
imported `field_validator`. The fixture is pydantic 2.13.5's own entry file, copied as installed (151 names).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.analysis import installed_packages, language_service, package_exports

CAPTURED = Path(__file__).parent / "captured" / "pydantic-2.13.5-init.py.txt"
BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")


def _pydantic(project: Path) -> None:
    package = project / ".venv" / "lib" / "python3.12" / "site-packages" / "pydantic"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(CAPTURED.read_text(encoding="utf-8"), encoding="utf-8")


def _wide_script_package(project: Path, count: int) -> None:
    """A package whose type file exports `count` functions, `name000` upward."""
    package = project / "node_modules" / "wide"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "wide", "types": "index.d.ts"}))
    (package / "index.d.ts").write_text(
        "".join(f"export declare function someLongExportedName{n:04d}(): void;\n" for n in range(count)))


def _tool(project: Path):
    [module_exports] = package_exports.exports_tools(project)
    return module_exports


def test_the_pydantic_list_holds_the_names_the_fixer_needed(tmp_path):
    _pydantic(tmp_path)

    answered = _tool(tmp_path).invoke({"module": "pydantic"})

    assert {"ValidationError", "field_validator", "model_validator", "BaseModel"} <= set(answered["exports"])
    assert answered["count"] == 151 and not answered.get("cut")
    assert "Only these names exist" not in answered["note"]


def test_a_list_past_the_budget_says_it_is_cut_and_how_many_there_are(tmp_path):
    _wide_script_package(tmp_path, 400)

    answered = _tool(tmp_path).invoke({"module": "wide"})

    assert answered["cut"] is True and answered["count"] == 400
    assert 0 < len(answered["exports"]) < 400
    assert "400" in answered["note"] and "`name`" in answered["note"]
    assert "only" not in answered["note"].lower()


@pytest.mark.parametrize("package, module, wanted", [
    (_pydantic, "pydantic", "field_validator"),
    (lambda root: _wide_script_package(root, 400), "wide", "someLongExportedName0399"),
])
def test_asked_for_one_name_it_says_the_package_exports_it(tmp_path, package, module, wanted):
    package(tmp_path)

    answered = _tool(tmp_path).invoke({"module": module, "name": wanted})

    assert answered["exported"] is True and f"`{wanted}`" in answered["note"]


def test_asked_for_a_name_it_lacks_it_gives_the_nearest(tmp_path):
    _pydantic(tmp_path)

    answered = _tool(tmp_path).invoke({"module": "pydantic", "name": "field_validators"})

    assert answered["exported"] is False and "field_validator" in answered["nearest"]


def test_the_readers_give_every_name(tmp_path):
    """The language service and the stuck-fix lookup read these lists too; a reader that cut them hid names."""
    _pydantic(tmp_path)
    _wide_script_package(tmp_path, 400)

    assert len(package_exports.python_package_exports(tmp_path, "pydantic")) == 151
    assert len(package_exports.script_package_exports(tmp_path, "wide")) == 400


def test_a_finding_about_a_package_with_many_names_says_its_list_is_cut_nearest_first(tmp_path):
    _wide_script_package(tmp_path, 400)
    importer = tmp_path / "src" / "app.ts"
    importer.parent.mkdir()
    finding = {"message": "Module '\"wide\"' has no exported member 'someLongExportedName0399x'.",
               "text": "import { someLongExportedName0399x } from 'wide';"}

    said = language_service.the_names_the_module_has(tmp_path, importer, finding)

    assert "exports only" not in said and "400 names" in said
    assert "someLongExportedName0399" in said


def test_the_stuck_fix_lookup_does_not_call_a_cut_list_the_only_names(tmp_path):
    _pydantic(tmp_path)

    found = installed_packages.answer(tmp_path, "ImportError: cannot import name 'field_validators' from 'pydantic'")

    assert found is not None
    assert "exports only" not in found.sentence and "151 names" in found.sentence
    assert "`field_validator`" in found.sentence


def test_the_defect_for_a_name_a_wide_package_lacks_says_its_list_is_cut(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.graph import engineering

    _wide_script_package(tmp_path, 400)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("import { someLongExportedName0399x } from 'wide';\n")
    finding = {"line": 1, "message": "Module '\"wide\"' has no exported member 'someLongExportedName0399x'.",
               "text": "import { someLongExportedName0399x } from 'wide';"}
    monkeypatch.setattr("app.graph.engineering.ci.changed_since", lambda root, since: ["src/app.ts"])
    monkeypatch.setattr("app.analysis.language_service.underlined_in",
                        lambda root, files, project, most: {"src/app.ts": [finding]})
    monkeypatch.setattr(engineering, "_what_the_compiler_says", lambda *a, **k: [])
    monkeypatch.setattr(engineering, "_owner_of", lambda state, text: "backend")

    [defect] = engineering.underlined_in_the_batch(SimpleNamespace(), str(tmp_path), "abc")

    assert "exports only" not in defect.expected_behavior and "400 names" in defect.expected_behavior
    assert "`someLongExportedName0399`" in defect.expected_behavior


def test_the_tool_s_answers_and_description_avoid_the_banned_words(tmp_path):
    _pydantic(tmp_path)
    _wide_script_package(tmp_path, 400)
    tool = _tool(tmp_path)
    answers = [tool.invoke({"module": "pydantic"}), tool.invoke({"module": "wide"}),
               tool.invoke({"module": "pydantic", "name": "field_validator"}),
               tool.invoke({"module": "pydantic", "name": "nothing_like_it"})]

    for text in [tool.description, json.dumps(tool.args)] + [a["note"] for a in answers]:
        assert not BANNED.search(text), text
