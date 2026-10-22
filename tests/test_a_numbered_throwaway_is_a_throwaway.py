"""`temp2.js` is a throwaway, as `temp_check.js` is.

One fix stage left `temp2.js`, `temp3.mjs`, `temp4.mjs` and `temp5.mjs` - Playwright
probes that launched a browser and printed a count. None was swept, because the
name rule allowed only a separator after `temp`. A test round reported a defect
in the first, a fix stage spent a pass converting it to `import`, and a testing
stage was refused seven times deleting it as product code.
"""

from __future__ import annotations

import pytest

from app.analysis import project_memory
from app.analysis.file_kinds import is_scratch
from app.tools.repository import (
    PROJECT_MARKER,
    clear_the_throwaways_left_behind,
    delete_approved_artifact,
    write_approved_artifact,
)

PROBE = "import { chromium } from '@playwright/test';\nconsole.log(await chromium.launch());\n"


@pytest.mark.parametrize("name", ["temp2.js", "temp5.mjs", "tmp1.js", "debug3.js", "temp_check.js"])
def test_a_numbered_probe_is_a_throwaway(name: str) -> None:
    assert is_scratch(f"app/{name}")


@pytest.mark.parametrize("name", ["template.js", "tempo.js", "temperature.js", "temp.config.js".replace(".config", "late")])
def test_a_word_that_starts_the_same_is_not(name: str) -> None:
    assert not is_scratch(f"app/{name}")


def test_the_sweep_removes_it(tmp_path) -> None:
    (tmp_path / PROJECT_MARKER).write_text("app\n", encoding="utf-8")
    write_approved_artifact(tmp_path, "app/package.json", '{"name": "app"}')
    write_approved_artifact(tmp_path, "app/app.js", "export const a = 1;\n")
    # Written as a stage of the run writes it: the sweep only touches files a
    # stage of this run created.
    (tmp_path / "app" / "temp2.js").write_text(PROBE, encoding="utf-8")
    project_memory.record(tmp_path, "app/temp2.js", "defect_fix_1_0")

    removed = clear_the_throwaways_left_behind(tmp_path)

    assert "app/temp2.js" in removed
    assert not (tmp_path / "app" / "temp2.js").exists()


def test_a_testing_stage_may_delete_one(tmp_path, monkeypatch) -> None:
    write_approved_artifact(tmp_path, "app/package.json", '{"name": "app"}')
    write_approved_artifact(tmp_path, "app/temp2.js", PROBE)
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "specialist_testing_0")

    delete_approved_artifact(tmp_path, "app/temp2.js")

    assert not (tmp_path / "app" / "temp2.js").exists()


def test_a_testing_stage_still_may_not_touch_the_product(tmp_path, monkeypatch) -> None:
    from app.tools.repository import RepositoryToolError

    write_approved_artifact(tmp_path, "app/package.json", '{"name": "app"}')
    write_approved_artifact(tmp_path, "app/app.js", "export const a = 1;\n")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "specialist_testing_0")

    with pytest.raises(RepositoryToolError, match="product code"):
        delete_approved_artifact(tmp_path, "app/app.js")
