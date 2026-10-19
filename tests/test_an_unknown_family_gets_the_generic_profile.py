"""A served model's family decides what the harness knows of it; an unknown one gets the generic profile (Initiative BH)."""
from __future__ import annotations

import re

from app.models import registry


def test_families_are_told_apart_by_the_served_name():
    assert registry.profile_for("unsloth/Qwen3.6-35B-A3B-MTP-GGUF").family == "qwen3"
    assert registry.profile_for("Qwen3-Coder-30B-A3B-Instruct").family == "qwen3-coder"
    assert registry.profile_for("mistralai/Devstral-Small-2507").family == "mistral"
    assert registry.profile_for("openai/gpt-oss-20b").family == "gpt-oss"


def test_an_unknown_family_gets_the_generic_profile():
    profile = registry.profile_for("some-new-model-7b")
    assert profile is registry.GENERIC and profile.budget_per_request is None


def test_sampling_is_advice_and_the_line_says_so():
    line = registry.describe("unsloth/Qwen3.6-35B-A3B-MTP-GGUF")
    assert "advice, never sent" in line and "edit preference unmeasured" in line
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", line, re.I)
