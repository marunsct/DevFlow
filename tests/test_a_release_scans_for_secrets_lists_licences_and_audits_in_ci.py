"""A release scans the product for credentials, lists its dependencies' licences and audits them in CI (plan PN.1).

Behind `RELEASE_AUDITS`, off until measured. A credential holds the release
back like a failing criterion; a strong-copyleft dependency is a gap; the
audit is a step of the generated CI, where its advisory database is reachable.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from types import SimpleNamespace
from unittest import mock

from app.graph import delivery
from app.stacks import contract, release, release_audits

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"RELEASE_AUDITS": "on"}
#: Built here, so this file never holds a credential's shape itself.
A_CLOUD_KEY = "AKIA" + "Q7" * 8


def _repository(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "settings.py").write_text(f'DEBUG = False\nKEY = "{A_CLOUD_KEY}"\n')
    (tmp_path / "app" / "main.py").write_text('import os\nKEY = os.environ["KEY"]\n')
    return tmp_path


def test_a_credential_in_the_code_is_named_with_its_file_and_line(tmp_path):
    root = _repository(tmp_path)
    with mock.patch.dict(os.environ, ON):
        found = release_audits.secrets_found(root)
    assert len(found) == 1 and "`app/settings.py` line 2" in found[0] and "cloud access key" in found[0]
    assert not BANNED.search(found[0])
    with mock.patch.dict(os.environ, {"RELEASE_AUDITS": ""}):
        assert release_audits.secrets_found(root) == []


def test_licences_are_listed_and_a_strong_copyleft_one_is_a_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "read", lambda root: {"project": "app"})
    site = tmp_path / "app" / ".venv" / "lib" / "python3.12" / "site-packages"
    for name, line in (("calm", "License-Expression: MIT"), ("bound", "Classifier: License :: OSI Approved :: GNU Affero General Public License v3"),
                       ("lesser", "License: LGPL-2.1")):
        (site / f"{name}-1.0.dist-info").mkdir(parents=True)
        (site / f"{name}-1.0.dist-info" / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\n{line}\n\nbody\n")
    (tmp_path / "app" / "node_modules" / "left-pad").mkdir(parents=True)
    (tmp_path / "app" / "node_modules" / "left-pad" / "package.json").write_text(json.dumps({"name": "left-pad", "license": "WTFPL"}))

    with mock.patch.dict(os.environ, ON):
        gaps = release_audits.licence_gaps(tmp_path)

    listing = (tmp_path / release_audits.LISTING).read_text()
    assert "| calm | MIT |" in listing and "| left-pad | WTFPL |" in listing and "| lesser | LGPL-2.1 |" in listing
    assert len(gaps) == 1 and "bound" in gaps[0] and "lesser" not in gaps[0] and "calm" not in gaps[0]


def test_the_ci_carries_the_ecosystem_s_audit_only_when_on():
    pack = SimpleNamespace(language="python", ci_setup=(), ci_prepare=(),
                           commands=lambda project, package: {"install": [["pip", "install", "."]],
                                                              "unit_test": ["pytest"], "acceptance_test": ["pytest", "a"]})
    with mock.patch.dict(os.environ, {"RELEASE_AUDITS": ""}):
        assert "pip-audit" not in release.ci_workflow(pack, "app", "App")
    with mock.patch.dict(os.environ, ON):
        # The product's own environment, not the runner's system pip.
        assert '- run: ".venv/bin/python -m pip install pip-audit && .venv/bin/python -m pip_audit"' in release.ci_workflow(pack, "app", "App")
    assert release_audits.audit_command(SimpleNamespace(language="go", audit="")) == ""


def test_the_release_holds_back_for_a_credential(tmp_path, monkeypatch):
    from app.analysis import integration_checks

    root = _repository(tmp_path)
    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: [])
    monkeypatch.setattr(contract, "the_pack", lambda root: None)
    with mock.patch.dict(os.environ, ON):
        held = delivery.release(
            {"repository": SimpleNamespace(root_path=str(root)), "release_attempts": 0}, {"configurable": {}},
            SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(root), allow_subdirectories=True),
        )
    assert held["stage"] == "technical_lead" and "cloud access key" in held["revision_comments"][-1]


def test_the_harness_s_and_toolchains_folders_and_documented_example_keys_are_not_the_product_s(tmp_path):
    """A seeded workspace has no harness ignore file, so a module cache's test keys were scanned; and a
    documented example key read as a credential."""
    root = _repository(tmp_path)
    (root / "app" / "settings.py").write_text('KEY = "' + "AKIA" + "IOSFODNN7" + 'EXAMPLE"\n')
    (root / ".agent-home" / "go").mkdir(parents=True)
    (root / ".agent-home" / "go" / "key_test.go").write_text(f'const k = "{A_CLOUD_KEY}"\n')
    with mock.patch.dict(os.environ, ON):
        assert release_audits.secrets_found(root) == []


def test_example_files_placeholders_nested_toolchain_dirs_are_not_credentials_and_java_has_an_audit(tmp_path):
    root = _repository(tmp_path)
    (root / "app" / "settings.py").write_text("KEY = 'x'\n")
    (root / "app" / ".env.example").write_text("GITHUB_TOKEN=ghp_" + "x" * 36 + "\nSTRIPE=sk_live_" + "x" * 24 + "\n")
    (root / "app" / "config.py").write_text("TOKEN = 'ghp_" + "a" * 36 + "'\n")  # one repeated character
    (root / "app" / "vendor" / "bundle").mkdir(parents=True)
    (root / "app" / "vendor" / "bundle" / "k.py").write_text(f'k = "{A_CLOUD_KEY}"\n')
    with mock.patch.dict(os.environ, ON):
        assert release_audits.secrets_found(root) == []
    assert "dependency-check" in release_audits.AUDIT_COMMANDS["java"]
