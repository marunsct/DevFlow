"""A fresh install keeps uploads and artifacts on the local filesystem; a half-set store credential is refused.

The setup script wrote `OBJECT_STORE_BUCKET=langchain-artifacts` and a MinIO password for a MinIO the compose file no
longer ships, so a fresh `.env` named a store nothing serves; and the compose file's default access key
(`minioadmin`) with a blank secret reached a store that takes a blank password, or failed on every call.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.server import object_store

ROOT = Path(__file__).resolve().parents[1]


def test_the_setup_script_writes_no_bucket(tmp_path):
    env = tmp_path / ".env"
    subprocess.run(["bash", str(ROOT / "scripts" / "setup-env.sh"), str(env)], check=True, capture_output=True)
    keys = {line.split("=", 1)[0] for line in env.read_text().splitlines() if "=" in line and not line.startswith("#")}
    assert "JWT_SECRET_KEY" in keys
    assert not keys & {"OBJECT_STORE_BUCKET", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"}


def test_the_example_settings_keep_files_locally():
    example = (ROOT / ".env.example").read_text()
    assert "\nOBJECT_STORE_BUCKET=\n" in example and "minio:9000" not in example


def test_the_compose_file_supplies_no_default_access_key():
    assert "MINIO_ROOT_USER:-minioadmin" not in (ROOT / "docker-compose.yml").read_text()


def test_a_bucket_with_a_key_and_an_empty_secret_is_refused(monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_BUCKET", "b")
    monkeypatch.setenv("OBJECT_STORE_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("OBJECT_STORE_SECRET_KEY", "")
    with pytest.raises(ValueError, match="OBJECT_STORE_SECRET_KEY is empty"):
        object_store.build_object_store()


def test_no_bucket_is_the_local_store_whatever_the_keys(monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_BUCKET", "")
    monkeypatch.setenv("OBJECT_STORE_ACCESS_KEY", "minioadmin")
    monkeypatch.delenv("OBJECT_STORE_SECRET_KEY", raising=False)
    assert isinstance(object_store.build_object_store(), object_store.LocalObjectStore)
