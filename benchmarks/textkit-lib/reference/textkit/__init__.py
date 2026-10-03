"""Text helpers."""
import re

__all__ = ["slugify", "word_count", "truncate", "title_case"]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def word_count(text: str) -> int:
    return len(text.split())


def truncate(text: str, limit: int, suffix: str = "...") -> str:
    if limit < len(suffix):
        raise ValueError("limit is shorter than the suffix")
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)] + suffix


def title_case(text: str) -> str:
    return re.sub(r"\S+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), text)
