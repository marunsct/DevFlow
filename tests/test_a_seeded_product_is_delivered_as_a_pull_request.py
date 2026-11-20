"""A completed seeded run delivers its change to the repository it came from (plan WS.7, `PULL_REQUEST_DELIVERY`).

A run seeded from a repository ended with the change in the run's own workspace, and the owner carried it back by
hand. With the switch on, the change is pushed as a branch and a pull request is opened when the owner gave a
delivery token, and is written as a bundle and a patch for download when not. The remote here is a local bare
repository standing in for the host (git's `insteadOf`), and the host's API is a recording spy: no network.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.observability.switch_firing import fired
from app.server import repository_delivery, seeding
from app.sprint import handover
from app.tools.repository import pin_the_directory_the_product_names
from app.tools.version_control import initialise_repository

HOSTED = "https://github.com/acme/shop.git"
TOKEN = "ghp_delivery_token_never_printed"
RUN = "run-0123456789abcdef"
NAME = "Add gift wrap at checkout"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout


def _an_origin(tmp_path: Path, files: dict[str, str]) -> Path:
    """A bare repository on branch main holding `files`, answering for the hosted URL."""
    source = tmp_path / "author"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    for name, text in files.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(text, encoding="utf-8")
    _git(source, "add", "-A")
    _git(source, "commit", "-q", "-m", "The product as it was")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "-q", "--bare", str(source), str(origin))
    return origin


class HostSpy:
    """The host's API: records every request it is sent and answers that the pull request is open."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, headers: dict, payload: dict) -> tuple[int, dict]:
        self.requests.append((url, headers, payload))
        return 201, {"html_url": "https://github.com/acme/shop/pull/7"}


@pytest.fixture
def host(tmp_path, monkeypatch) -> HostSpy:
    origin = _an_origin(tmp_path, {"src/cart.py": "def total():\n    return 0\n", "README.md": "# Shop\n",
                                   "old_notes.txt": "to be removed\n"})
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.file://{origin}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", HOSTED)
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "https,file")
    monkeypatch.setenv("SEED_ALLOW_PRIVATE_HOSTS", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RUN_TRANSCRIPT", "true")
    monkeypatch.setenv("PULL_REQUEST_DELIVERY", "on")
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    spy = HostSpy()
    monkeypatch.setattr(repository_delivery, "_post_json", spy)
    return spy


def _a_seeded_run(tmp_path: Path, *, token: str | None, move: bool = False) -> Path:
    """Seed a workspace from the hosted URL as a run's start does, then make the run's change and commit it."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = SimpleNamespace(type="git", url=HOSTED, ref="main", token=None, depth=1, delivery_token=token)
    seeding.seed_workspace(workspace, source, resolve_upload=None)
    initialise_repository(workspace)
    repository_delivery.remember(RUN, workspace, source)
    product = workspace
    if move:
        product = workspace / pin_the_directory_the_product_names(workspace, "Shop")
    (product / "src" / "cart.py").write_text("def total(wrapped=False):\n    return 5 if wrapped else 0\n", encoding="utf-8")
    (product / "src" / "wrap.py").write_text("def wrap():\n    return 'wrapped'\n", encoding="utf-8")
    (product / "old_notes.txt").unlink()
    (workspace / "docs").mkdir(exist_ok=True)
    (workspace / "docs" / "sprint_1_summary.md").write_text("# Sprint 1 Summary\n\nGift wrap is offered.\n", encoding="utf-8")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "Sprint 1")
    return workspace


def _branch_files(origin: Path, branch: str) -> dict[str, str]:
    names = _git(origin, "ls-tree", "-r", "--name-only", branch).split()
    return {name: _git(origin, "show", f"{branch}:{name}") for name in names}


def test_a_change_with_a_delivery_token_is_pushed_as_a_branch_and_opened_as_a_pull_request(tmp_path, host):
    workspace = _a_seeded_run(tmp_path, token=TOKEN)

    outcome = repository_delivery.deliver(RUN, workspace, name=NAME)

    assert (outcome.kind, outcome.url) == ("pull_request", "https://github.com/acme/shop/pull/7")
    assert _branch_files(tmp_path / "origin.git", outcome.branch) == {
        "README.md": "# Shop\n",
        "src/cart.py": "def total(wrapped=False):\n    return 5 if wrapped else 0\n",
        "src/wrap.py": "def wrap():\n    return 'wrapped'\n",
    }
    assert _git(tmp_path / "origin.git", "rev-parse", f"{outcome.branch}^").strip() == \
        _git(tmp_path / "origin.git", "rev-parse", "main").strip()
    [(url, headers, payload)] = host.requests
    assert url == "https://api.github.com/repos/acme/shop/pulls"
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert (payload["head"], payload["base"], payload["title"]) == (outcome.branch, "main", NAME)
    assert "Gift wrap is offered." in payload["body"]


def test_the_token_is_in_no_file_of_the_workspace_and_no_record_of_the_run(tmp_path, host):
    workspace = _a_seeded_run(tmp_path, token=TOKEN)

    outcome = repository_delivery.deliver(RUN, workspace, name=NAME)

    kept = [path for path in [*workspace.rglob("*"), *(tmp_path / "data").rglob("*")] if path.is_file()]
    assert not [path for path in kept if TOKEN.encode() in path.read_bytes()]
    assert TOKEN not in json.dumps(outcome.as_dict())


def test_a_product_the_run_moved_into_its_directory_is_delivered_where_the_repository_keeps_it(tmp_path, host):
    workspace = _a_seeded_run(tmp_path, token=TOKEN, move=True)

    outcome = repository_delivery.deliver(RUN, workspace, name=NAME)

    assert sorted(_branch_files(tmp_path / "origin.git", outcome.branch)) == ["README.md", "src/cart.py", "src/wrap.py"]


def test_without_a_delivery_token_the_change_is_a_bundle_and_a_patch_in_the_handover_pack(tmp_path, host):
    workspace = _a_seeded_run(tmp_path, token=None)

    outcome = repository_delivery.deliver(RUN, workspace, name=NAME)

    assert outcome.kind == "bundle" and "no delivery token" in outcome.message
    assert host.requests == []
    assert _git(tmp_path / "origin.git", "branch", "--list", "harness/*").strip() == ""
    assert set(outcome.files) <= set(handover.files_of(workspace)) and len(outcome.files) == 2
    clone = tmp_path / "reviewer"
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(clone))
    patch = next(workspace / name for name in outcome.files if name.endswith(".patch"))
    _git(clone, "am", "-q", str(patch))
    assert (clone / "src" / "wrap.py").is_file() and not (clone / "old_notes.txt").exists()


def test_the_delivery_is_the_switch_s_firing_signal(tmp_path, host):
    workspace = _a_seeded_run(tmp_path, token=TOKEN)

    repository_delivery.deliver(RUN, workspace, name=NAME)

    path = tmp_path / "data" / "transcripts" / f"{RUN}.jsonl"
    assert fired(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()) == ["PULL_REQUEST_DELIVERY"]


def test_with_the_switch_off_nothing_is_delivered(tmp_path, host, monkeypatch):
    monkeypatch.setenv("PULL_REQUEST_DELIVERY", "off")
    workspace = _a_seeded_run(tmp_path, token=TOKEN)

    assert repository_delivery.deliver(RUN, workspace, name=NAME) is None
    assert host.requests == [] and not (tmp_path / "data" / "delivery-credentials").exists()


@pytest.mark.parametrize(("name", "branch"), [
    ("Add gift wrap at checkout", "harness/add-gift-wrap-at-checkout-89abcdef"),
    ("  ../Ünïcode: name? *[x]~^ .lock", "harness/n-code-name-x-.lock-89abcdef"),
    ("", "harness/change-89abcdef"),
], ids=["words", "characters no host takes", "no name"])
def test_the_branch_is_named_from_the_run_in_characters_every_host_takes(name, branch):
    made = repository_delivery.branch_name(name, RUN)

    assert made == branch
    assert subprocess.run(["git", "check-ref-format", f"refs/heads/{made}"]).returncode == 0


def test_a_run_started_with_a_delivery_token_keeps_it_sealed_outside_the_workspace(client, host, tmp_path):
    """Through the start endpoint: what the change is delivered against is recorded, and the token is nowhere readable."""
    import os

    created = client.post("/api/runs", files=[("files", ("brief.md", b"# Add gift wrap", "text/markdown"))])
    run_id = created.json()["run_id"]

    started = client.post(f"/api/runs/{run_id}/start", json={"source": {
        "type": "git", "url": HOSTED, "ref": "main", "delivery_token": TOKEN}})

    assert started.status_code == 202, started.text
    root = Path(os.environ["WORKFLOW_WORKSPACE_ROOT"])
    [workspace] = list(root.glob(f"*{run_id}")) or list(root.glob(f"*/*{run_id}"))
    recorded = json.loads((workspace / repository_delivery.RECORD).read_text(encoding="utf-8"))
    assert (recorded["url"], recorded["base_ref"]) == (HOSTED, "main") and len(recorded["base_commit"]) == 40
    sealed = list((tmp_path / "data" / "delivery-credentials").iterdir())
    assert len(sealed) == 1 and TOKEN.encode() not in sealed[0].read_bytes()
    assert not [path for path in workspace.rglob("*") if path.is_file() and TOKEN.encode() in path.read_bytes()]
