"""A command that ran with no network and could not resolve a host measured the product: what it needed was not installed.

Measured on a Rust run: the product's manifest asked for a feature its dependency does not have, the networked install
failed (cargo exit 101), and every offline test build then printed "Could not resolve host: index.crates.io" - read as
"the harness could not measure", so five measurements judged nothing about a product that could not build.
"""
from __future__ import annotations

from app.acceptance import unmeasured

OFFLINE_BUILD = {"returncode": "101", "stdout": "", "network": "none",
                 "stderr": "error: failed to get `axum` as a dependency\nCould not resolve host: index.crates.io"}


def test_an_offline_build_that_cannot_reach_the_registry_is_measured():
    assert unmeasured.why(OFFLINE_BUILD) == ""


def test_a_networked_install_that_cannot_resolve_the_registry_is_not_measured():
    assert "could not resolve" in unmeasured.why({**OFFLINE_BUILD, "network": "bridge"})


def test_an_outcome_that_does_not_say_its_network_reads_as_before():
    without = {key: value for key, value in OFFLINE_BUILD.items() if key != "network"}

    assert "could not resolve" in unmeasured.why(without)
