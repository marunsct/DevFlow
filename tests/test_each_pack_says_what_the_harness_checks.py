"""Each pack says what the harness checks on it, and every service pack names its stub (Initiative AW).

The support tier said a product was "pack-supported" and nothing about what that
bought: a Go service and a React page were the same sentence. And the check that
the served code is the run's own rather than the scaffold's stub (K.3) reached
only the packs that named an entrypoint - eleven service and fullstack packs did not.
"""
from __future__ import annotations

import re

from app.stacks import pack_named, support_tier
from app.stacks.packs import ALL_PACKS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: A service whose routes are new files the framework finds by itself: no stub to outgrow.
NO_STUB = {"java-spring-api"}


def test_every_service_and_fullstack_pack_names_the_file_its_product_replaces():
    for pack in ALL_PACKS:
        if pack.name in NO_STUB or not (pack.kind == "fullstack" or "api" in pack.name):
            continue
        named = [e for e in (pack.entrypoint, *pack.entrypoints) if e]
        assert named, pack.name
        assert all(e in pack.files and e not in pack.kept_files for e in named), pack.name


def test_the_tier_says_what_is_checked_and_differs_by_pack():
    page = support_tier(pack_named("fullstack-react-fastapi"))
    service = support_tier(pack_named("go-http-api"))

    assert "What the harness checks on it:" in page
    assert "the page in a browser" in page and "imports against the packages" in page
    assert "the page in a browser" not in service and "`server.go`" in service
    for pack in ALL_PACKS:
        assert not BANNED.search(" ".join(pack.coverage)), pack.name
