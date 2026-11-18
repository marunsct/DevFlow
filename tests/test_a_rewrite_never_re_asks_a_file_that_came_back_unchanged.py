"""A fix's rewrite does not ask again for a file that came back unchanged, nor offer another ecosystem's manifest.

Deep review 2026-11-18, item A5: in the one-call rewrite path 194 of 462 replies (42%) returned the file unchanged, and
every pass asked again for every file the failure text named - including a `package.json` rewritten in a Rust project.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import rewritten_fixes
from app.stacks import contract, pack_named


def _write(base, path, content):
    from pathlib import Path

    (Path(base) / path).write_text(content)


def test_a_file_sent_back_unchanged_is_not_asked_for_again(tmp_path):
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app/src/store.ts").write_text("export const store = 0;\n")
    (tmp_path / "app/src/routes.ts").write_text("export const routes = [];\n")
    defect = SimpleNamespace(description="The service does not start", expected_behavior="It starts",
                             affected_files=["app/src/store.ts", "app/src/routes.ts"],
                             actual_behavior="app/src/store.ts:1 failed", reproduction_steps=[])
    asked: list[str] = []

    class Model:
        def invoke(self, messages, **kwargs):
            request = messages[-1].content
            which = "app/src/routes.ts" if "content of `app/src/routes.ts`" in request else "app/src/store.ts"
            current = (tmp_path / which).read_text()
            asked.append(which)
            if which == "app/src/routes.ts":
                return SimpleNamespace(content=f"```ts\n{current}```")
            return SimpleNamespace(content=f"```ts\nexport const store = {len(asked)};\n```")

    still_failing = ["- In the project line 1: the build still fails"]
    rewritten_fixes.fix_by_rewriting(defect, tmp_path, Model(), write=_write, diagnose=lambda files: still_failing)

    assert asked.count("app/src/routes.ts") == 1
    assert asked.count("app/src/store.ts") == rewritten_fixes.MOST_PASSES


DEFECT = SimpleNamespace(description="The command fails", expected_behavior="It counts", affected_files=[],
                         actual_behavior="error at app/src/main.rs:3:5\nsee app/package.json", reproduction_steps=[])


def _project(root, pack, *files):
    contract.write(root, pack_named(pack), "app", "Counter")
    for name in files:
        (root / "app" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "app" / name).write_text("x\n")


def test_a_manifest_of_another_ecosystem_is_not_offered_to_a_rewrite(tmp_path):
    _project(tmp_path, "rust-cli", "src/main.rs", "package.json")
    failure = rewritten_fixes.what_failed(DEFECT, tmp_path)

    files = rewritten_fixes.files_to_fix(DEFECT, failure, tmp_path, lambda path: True)

    assert "app/src/main.rs" in files and "app/package.json" not in files


def test_a_page_s_manifest_in_a_project_with_a_page_is_still_offered(tmp_path):
    _project(tmp_path, "fullstack-react-fastapi", "src/main.rs", "package.json")
    failure = rewritten_fixes.what_failed(DEFECT, tmp_path)

    files = rewritten_fixes.files_to_fix(DEFECT, failure, tmp_path, lambda path: True)

    assert "app/package.json" in files
