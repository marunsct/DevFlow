"""The handoff score sees a port read as Rust reads it and as a Spring configuration names it (found on the sweep).

Measured on the language sweep: notes-api-rust (`env::var("PORT")`) and notes-api-java (`server.port=${PORT:8080}` in
`application.properties`) both read the port and both lost the handoff point for not reading it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _score():
    spec = importlib.util.spec_from_file_location("bench_score_port", ROOT / "scripts" / "bench" / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _product(tmp_path, relative, text):
    (tmp_path / "start.sh").write_text("#!/bin/sh\nexec ./run\n")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return tmp_path


def test_rust_reading_the_port_counts(tmp_path):
    product = _product(tmp_path, "src/main.rs", 'let port = env::var("PORT").unwrap_or_else(|_| "3000".into());\n')
    assert _score().handoff(product)["handoff"]["start_reads_its_port"] is True


def test_a_spring_configuration_naming_the_port_counts(tmp_path):
    product = _product(tmp_path, "src/main/resources/application.properties", "server.port=${PORT:8080}\n")
    assert _score().handoff(product)["handoff"]["start_reads_its_port"] is True


def test_a_product_that_reads_no_port_still_does_not_count(tmp_path):
    product = _product(tmp_path, "src/main.rs", 'let port = 3000;\n')
    assert _score().handoff(product)["handoff"]["start_reads_its_port"] is False
