"""A product seeded at the workspace root moves into the directory intake pins (plan LF.520)."""
from __future__ import annotations

import json
import re
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from app.acceptance import suite
from app.acceptance.regression_contract import mark_seeded
from app.graph import acceptance_nodes
from app.server import seeding
from app.stacks import custom_setup
from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory
from app.tools.version_control import initialise_repository

ROOT = Path(__file__).resolve().parents[1]
NAME = "Tasks API"
PROJECT = "tasks-api"
BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _seeded(tmp_path: Path, files: dict[str, str], *, one_folder: bool = True, git: bool = True) -> Path:
    """A workspace seeded through the real archive path, as a run's start does it."""
    source = tmp_path / "upload" / ("product" if one_folder else "")
    for name, text in files.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(text, encoding="utf-8")
    archive = tmp_path / "base.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for entry in sorted((tmp_path / "upload").iterdir()):
            tar.add(entry, arcname=entry.name)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    seeding.seed_workspace(
        workspace, SimpleNamespace(type="archive", upload_id="base"), resolve_upload=lambda _: str(archive),
    )
    if git:
        initialise_repository(workspace)
    return workspace


PRODUCT = {"server.py": "print('serving')\n", "start.sh": "exec python server.py\n", "src/util.py": "VALUE = 1\n"}


def test_a_root_seed_moves_with_its_history_and_the_harness_records_stay(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT)
    (workspace / "docs").mkdir()
    (workspace / "docs" / "product_intake.md").write_text("intake\n", encoding="utf-8")

    assert pin_the_directory_the_product_names(workspace, NAME) == PROJECT

    project = workspace / PROJECT
    assert (project / "server.py").is_file() and (project / "start.sh").is_file() and (project / "src" / "util.py").is_file()
    assert not (workspace / "server.py").exists() and not (workspace / "start.sh").exists()
    assert (workspace / ".harness" / "seeded.json").is_file() and (workspace / ".git").is_dir()
    assert (workspace / "docs" / "product_intake.md").is_file() and not (project / "docs").exists()
    # The harness's own ignore list stays where it keeps the harness's records out of history.
    assert (workspace / ".gitignore").is_file() and not (project / ".gitignore").exists()
    history = subprocess.run(
        ["git", "log", "--follow", "--format=%s", "--", f"{PROJECT}/server.py"],
        cwd=workspace, capture_output=True, text=True, check=True,
    ).stdout
    assert "Baseline" in history and "Moved the seeded product" in history


def test_a_root_seed_with_no_repository_is_moved_plainly(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT, git=False)

    pin_the_directory_the_product_names(workspace, NAME)

    assert (workspace / PROJECT / "server.py").is_file() and not (workspace / "server.py").exists()


def test_a_seed_s_own_ignore_file_goes_with_the_product(tmp_path):
    workspace = _seeded(tmp_path, {**PRODUCT, ".gitignore": "*.log\n"}, git=False)

    pin_the_directory_the_product_names(workspace, NAME)

    moved = workspace / PROJECT / ".gitignore"
    assert moved.is_file() and moved.read_text(encoding="utf-8") == "*.log\n"


def test_a_greenfield_workspace_is_left_alone(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text("mine\n", encoding="utf-8")

    assert pin_the_directory_the_product_names(workspace, NAME) == PROJECT

    assert (workspace / "notes.md").is_file() and list((workspace / PROJECT).iterdir()) == []


def test_a_seed_in_a_project_folder_is_left_alone(tmp_path):
    workspace = _seeded(tmp_path, {"billing/server.py": "x = 1\n", "README.md": "read me\n"}, one_folder=False, git=False)

    assert pin_the_directory_the_product_names(workspace, NAME) is None

    assert (workspace / "README.md").is_file() and (workspace / "billing" / "server.py").is_file()
    assert pinned_project_directory(workspace) is None


def test_a_later_pin_of_the_seed_s_own_folder_moves_nothing_into_it(tmp_path):
    workspace = _seeded(tmp_path, {"billing/server.py": "x = 1\n", "README.md": "read me\n"}, one_folder=False, git=False)
    (workspace / ".project-directory").write_text("billing\n", encoding="utf-8")

    pin_the_directory_the_product_names(workspace, NAME)

    assert (workspace / "README.md").is_file() and not (workspace / "billing" / "README.md").exists()


def test_a_second_visit_does_nothing_whatever_was_written_since(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT)
    pin_the_directory_the_product_names(workspace, NAME)
    assert (workspace / PROJECT / "server.py").is_file()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True).stdout
    # A file by a seed's name written at the root after the move, by whoever.
    (workspace / "server.py").write_text("later\n", encoding="utf-8")

    assert pin_the_directory_the_product_names(workspace, NAME) is None

    assert (workspace / "server.py").read_text(encoding="utf-8") == "later\n"
    assert (workspace / PROJECT / "server.py").read_text(encoding="utf-8") == PRODUCT["server.py"]
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True).stdout == head


def test_a_name_already_taken_in_the_directory_is_not_overwritten(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT, git=False)
    (workspace / PROJECT).mkdir()
    (workspace / PROJECT / "start.sh").write_text("theirs\n", encoding="utf-8")
    (workspace / ".project-directory").write_text(f"{PROJECT}\n", encoding="utf-8")

    pin_the_directory_the_product_names(workspace, NAME)

    assert (workspace / PROJECT / "start.sh").read_text(encoding="utf-8") == "theirs\n"
    assert (workspace / "start.sh").read_text(encoding="utf-8") == PRODUCT["start.sh"]
    assert (workspace / PROJECT / "server.py").is_file()


def test_a_file_standing_where_the_directory_would_go_stops_the_move(tmp_path):
    workspace = _seeded(tmp_path, {**PRODUCT, PROJECT: "a file\n"}, git=False)

    pin_the_directory_the_product_names(workspace, NAME)

    assert (workspace / PROJECT).read_text(encoding="utf-8") == "a file\n" and (workspace / "server.py").is_file()


def test_the_move_is_in_the_run_s_decisions_once(tmp_path):
    assert "record_the_move(state, update)" in (ROOT / "src/app/graph/workflow.py").read_text(encoding="utf-8")
    from app.stacks.seeded_product import record_the_move

    workspace = _seeded(tmp_path, PRODUCT, git=False)
    pin_the_directory_the_product_names(workspace, NAME)
    state = {"repository": SimpleNamespace(root_path=str(workspace)), "decisions": []}
    update: dict = {}

    record_the_move(state, update)
    record_the_move(state, update)

    assert len(update["decisions"]) == 1
    record = update["decisions"][0]
    assert PROJECT in record["decision"] and "server.py" in record["rationale"]
    assert not BANNED.search(re.sub(re.escape(PROJECT), "", record["question"] + record["rationale"]))


def test_a_greenfield_run_records_no_move(tmp_path):
    from app.stacks.seeded_product import record_the_move

    update: dict = {}
    record_the_move({"repository": SimpleNamespace(root_path=str(tmp_path))}, update)
    assert update == {}


# --- already set up -----------------------------------------------------------


def test_a_seeded_product_with_code_and_no_manifest_is_already_set_up(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT, git=False)
    pin_the_directory_the_product_names(workspace, NAME)

    assert custom_setup.already_set_up(workspace / PROJECT) is True


def test_a_seed_with_no_code_still_gets_a_setup(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / PROJECT).mkdir(parents=True)
    (workspace / PROJECT / "README.md").write_text("words\n", encoding="utf-8")
    mark_seeded(workspace, {"type": "archive"})

    assert custom_setup.already_set_up(workspace / PROJECT) is False


def test_the_same_code_in_a_run_that_started_empty_is_not_set_up(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / PROJECT).mkdir(parents=True)
    (workspace / PROJECT / "server.py").write_text("x = 1\n", encoding="utf-8")

    assert custom_setup.already_set_up(workspace / PROJECT) is False


def _scaffold_node(workspace: Path, pack: str | None, **state: object) -> dict:
    full = {
        "repository": SimpleNamespace(root_path=str(workspace)),
        "stack_pack": pack,
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(language="python")),
        "product_intake": SimpleNamespace(product_name=NAME),
        **state,
    }
    ctx = SimpleNamespace(model=None, checkpointer=None, repo_root=str(workspace), allow_subdirectories=True)
    return acceptance_nodes.scaffold(full, {"configurable": {}}, ctx)


@pytest.mark.parametrize("files", [PRODUCT, {**PRODUCT, "requirements.txt": "httpx\n"}], ids=["no manifest", "a manifest"])
def test_no_pack_is_laid_over_a_seeded_product(tmp_path, files):
    workspace = _seeded(tmp_path, files, git=False)
    pin_the_directory_the_product_names(workspace, NAME)

    with mock.patch("app.stacks.scaffold.scaffold") as scaffold_pack:
        done = _scaffold_node(workspace, "python-http-api")

    scaffold_pack.assert_not_called()
    assert done["stage"] == "acceptance_author" and done["stack_pack"] is None
    # `ok`, or the release reports a setup that was never proven.
    assert done["scaffold_result"]["ok"] is True


def test_the_setup_stage_is_not_run_on_a_seeded_product(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT, git=False)
    pin_the_directory_the_product_names(workspace, NAME)

    with mock.patch("app.agents.specialists.create_specialist_agent"), \
            mock.patch("app.graph.workflow._run_gated_agent", return_value={"stage": "stack_setup_0"}) as stage, \
            mock.patch.object(custom_setup, "replay", return_value=[]):
        done = _scaffold_node(workspace, None)

    stage.assert_not_called()
    assert done["stage"] == "acceptance_author"


def test_a_setup_stage_already_begun_goes_on(tmp_path):
    workspace = _seeded(tmp_path, {"README.md": "words\n"}, git=False)
    pin_the_directory_the_product_names(workspace, NAME)
    (workspace / PROJECT / "server.py").write_text("the smallest app\n", encoding="utf-8")

    with mock.patch("app.agents.specialists.create_specialist_agent"), \
            mock.patch("app.graph.workflow._run_gated_agent", return_value={"stage": "stack_setup_1"}) as stage:
        _scaffold_node(workspace, None, scaffold_result={"ok": False, "setup_attempts": 1})

    stage.assert_called_once()


def test_with_no_setup_the_suite_declares_its_command_in_the_moved_project(tmp_path):
    workspace = _seeded(tmp_path, PRODUCT, git=False)
    pin_the_directory_the_product_names(workspace, NAME)
    assert (workspace / PROJECT / "server.py").is_file()

    where = suite.location(workspace)
    assert where is not None and where[0] == PROJECT
    (workspace / PROJECT / where[1]).mkdir(parents=True)
    (workspace / PROJECT / where[1] / suite.DECLARED_COMMAND_FILE).write_text(
        json.dumps({"command": ["python", "-m", "pytest"], "report": "report.xml"}), encoding="utf-8",
    )
    assert suite._command(workspace)[0] == ["python", "-m", "pytest"]
