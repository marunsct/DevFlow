"""Every web pack's stylesheet starts with the shared design tokens (owner decision 2026-10-18, plan item A).

Products started from browser defaults: unstyled controls, no focus ring and
nothing a contrast audit could rely on. The tokens are custom properties, so
a product can change every value; the names are the contract.
"""
from __future__ import annotations

import re

from app.stacks.packs import ALL_PACKS
from app.stacks.packs._design import DESIGN_TOKENS

WEB_KINDS = {"browser_app", "fullstack"}


def _stylesheets(pack):
    return {path: text for path, text in pack.files.items() if path.endswith(".css") and text.strip()}


def test_every_web_pack_s_stylesheet_starts_with_the_tokens():
    web = [pack for pack in ALL_PACKS if pack.kind in WEB_KINDS]
    assert web
    for pack in web:
        sheets = _stylesheets(pack)
        assert sheets, pack.name
        assert any(text.startswith(DESIGN_TOKENS) for text in sheets.values()), pack.name


def test_the_tokens_cover_colour_space_type_and_focus_in_both_schemes():
    for name in ("--color-bg", "--color-text", "--color-primary", "--space-4", "--font-size-md", "--color-focus"):
        assert name in DESIGN_TOKENS
    assert "prefers-color-scheme: dark" in DESIGN_TOKENS
    assert ":focus-visible" in DESIGN_TOKENS


def _luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_text_colours_pass_aa_on_their_background_in_both_schemes():
    light, _, dark = DESIGN_TOKENS.partition("prefers-color-scheme: dark")
    for scheme in (light, dark):
        values = dict(re.findall(r"(--color-[a-z-]+): (#[0-9a-f]{6})", scheme))
        for text in ("--color-text", "--color-muted", "--color-primary", "--color-danger"):
            assert _contrast(values[text], values["--color-bg"]) >= 4.5, (text, values[text])
        assert _contrast(values["--color-on-primary"], values["--color-primary"]) >= 4.5
