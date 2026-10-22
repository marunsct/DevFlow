"""A milestone reviewer whose model reads images is shown the page; one that cannot is not.

Every check of a product was about function, and two mechanical checks now
catch a page nothing styled and one wider than a phone. Whether the page
matches its interface design takes eyes: the page probe keeps a screenshot at a
desktop's width and a phone's, and a reviewer that can see is given both. A
model that cannot is sent nothing - a refused request would cost the stage.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.page_screenshots import MOST_BYTES, with_the_page_screenshots
from app.models.vision import reads_images
from app.stacks import contract, pack_named

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _settings(provider: str = "local", name: str = "m", choice: str = "auto") -> SimpleNamespace:
    return SimpleNamespace(llm_provider=provider, model_name=name, model_reads_images=choice)


class TestWhetherTheModelSees:
    @pytest.mark.parametrize("provider, name", [
        ("anthropic", "claude-sonnet-5-5"),
        ("gemini", "gemini-2.5-pro"),
        ("local", "qwen2.5-vl-7b-instruct"),
        ("local", "llava-v1.6-mistral-7b"),
        ("openai", "gpt-4o-mini"),
        ("local", "Qwen/Qwen3-VL-30B-A3B"),
    ])
    def test_known_families_that_see(self, provider, name) -> None:
        assert reads_images(_settings(provider, name))

    @pytest.mark.parametrize("name", ["openai/gpt-oss-20b", "qwen3.6-35b-a3b-mtp", "zai-org/glm-4.7-flash", "mystery-model"])
    def test_a_model_it_cannot_place_does_not(self, name) -> None:
        assert not reads_images(_settings("local", name))

    def test_the_owner_s_word_decides(self) -> None:
        assert reads_images(_settings("local", "mystery-model", "yes"))
        assert not reads_images(_settings("anthropic", "claude-sonnet-5-5", "no"))


def _with_screenshots(root: Path, sizes: tuple[int, int] = (64, 64)) -> None:
    contract.write(root, pack_named("browser-javascript"), "notes", "Notes")
    folder = root / "notes" / "test-results"
    folder.mkdir(parents=True)
    for name, size in zip(("page-desktop.png", "page-phone.png"), sizes):
        (folder / name).write_bytes(PNG[:8] + b"\x00" * size)


REQUEST = {"messages": [{"role": "user", "content": "Review the milestone."}]}


class TestTheReviewIsShown:
    @pytest.fixture(autouse=True)
    def mock_reads_images(self, monkeypatch) -> None:
        import app.models.vision
        monkeypatch.setattr(app.models.vision, "the_reviewer_reads_images", lambda: True)

    def test_both_screenshots_follow_the_text_with_the_design(self, tmp_path) -> None:
        _with_screenshots(tmp_path)

        sent = with_the_page_screenshots(REQUEST, tmp_path, ["Below 600px the form sits above the list."])

        parts = sent["messages"][-1]["content"]
        assert parts[0]["type"] == "text" and parts[0]["text"].startswith("Review the milestone.")
        assert "Below 600px the form sits above the list." in parts[0]["text"]
        assert [p["type"] for p in parts[1:]] == ["image_url", "image_url"]
        assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_none_kept_leaves_the_request_as_it_was(self, tmp_path) -> None:
        assert with_the_page_screenshots(REQUEST, tmp_path) is REQUEST

    def test_one_too_large_to_send_is_left_out(self, tmp_path) -> None:
        _with_screenshots(tmp_path, sizes=(64, MOST_BYTES + 1))

        parts = with_the_page_screenshots(REQUEST, tmp_path)["messages"][-1]["content"]

        assert len(parts) == 2 and "a desktop's width" in parts[0]["text"]

    def test_the_note_names_no_product_and_no_control(self, tmp_path) -> None:
        _with_screenshots(tmp_path)
        text = with_the_page_screenshots(REQUEST, tmp_path)["messages"][-1]["content"][0]["text"].lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{word}\b", text), word

    def test_when_the_reviewer_cannot_read_images_none_are_sent(self, tmp_path, monkeypatch) -> None:
        _with_screenshots(tmp_path)
        import app.models.vision
        monkeypatch.setattr(app.models.vision, "the_reviewer_reads_images", lambda: False)
        
        sent = with_the_page_screenshots(REQUEST, tmp_path)
        
        assert sent is REQUEST



def test_the_setting_is_one_an_owner_can_change() -> None:
    from app.config import load_settings
    from app.server.runtime_settings import SETTABLE_KEYS

    assert SETTABLE_KEYS["model_reads_images"] == "MODEL_READS_IMAGES"
    assert load_settings({"MODEL_READS_IMAGES": "Yes"}).model_reads_images == "yes"
    assert load_settings({}).model_reads_images == "auto"
