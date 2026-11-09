"""The page's screenshots, given to a reviewer whose model can see them.

Every check of a product so far is about function. Two mechanical checks now
catch a page nothing styled and a page wider than a phone
(`app.analysis.interface_checks`); whether it matches its interface design,
whether controls can be told apart, whether it reads well - that takes eyes. The
harness's page probe keeps a screenshot at a desktop's width and at a phone's
on every run of the suite (`app.stacks.packs._javascript.page_check`); a
milestone reviewer that reads images is shown both.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Sequence

#: The screenshots the page probe keeps, and how each is described.
SCREENSHOTS = (
    ("page-desktop.png", "at a desktop's width (1280px)"),
    ("page-phone.png", "at a phone's width (375px)"),
)

#: A screenshot larger than this is left out rather than sent: a page that long
#: is better judged by its parts than by one image the model must shrink.
MOST_BYTES = 1_500_000


def _the_screenshots(repo_root: str | Path) -> list[tuple[str, bytes]]:
    from app.stacks import contract

    record = contract.read(repo_root) or {}
    folder = Path(repo_root) / str(record.get("project") or "") / "test-results"
    found = []
    for name, described in SCREENSHOTS:
        path = folder / name
        try:
            if path.is_file() and 0 < path.stat().st_size <= MOST_BYTES:
                found.append((described, path.read_bytes()))
        except OSError:
            continue
    return found


#: What a fixer is told of the screenshots after its request.
FIXER_NOTE = (
    "\n\n--- How the page looks now ---\n"
    "After this text are screenshots of the page as it first loads, before anything is done on it: {shots}. "
    "Use them to see what a person sees - what is missing, misplaced, unstyled or cut off - and fix what the "
    "defect is about in the code; they show the page before your change."
)


def _with_images(request: dict[str, Any], shots: list[tuple[str, bytes]], note: str) -> dict[str, Any]:
    messages = list(request.get("messages") or [])
    last = dict(messages[-1])
    text = last.get("content")
    if not isinstance(text, str):
        return request
    last["content"] = [
        {"type": "text", "text": text + note},
        *({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}}
          for _, data in shots),
    ]
    return {**request, "messages": [*messages[:-1], last]}


def with_the_page_for_a_fixer(request: dict[str, Any], repo_root: str | Path) -> dict[str, Any]:
    """A fix request with the page's screenshots, when the build model reads images and the page has them.

    Only the reviewer was shown the page: a layout fault reached the fixer as
    the reviewer's words about it. Never raises: a fix without pictures is the
    fix there was before.
    """
    try:
        from app.models.vision import the_build_model_reads_images

        shots = _the_screenshots(repo_root)
        if not shots or not request.get("messages") or not the_build_model_reads_images():
            return request
        return _with_images(request, shots, FIXER_NOTE.format(shots=" and ".join(d for d, _ in shots)))
    except Exception:  # noqa: BLE001
        return request


def with_the_page_screenshots(
    request: dict[str, Any], repo_root: str | Path, interface_design: Sequence[str] = ()
) -> dict[str, Any]:
    """`request` with the page's screenshots after its text, or unchanged when there are none.

    Never raises: a review without pictures is the review there was before.
    """
    try:
        from app.models.vision import the_reviewer_reads_images
        if not the_reviewer_reads_images():
            return request
        
        shots = _the_screenshots(repo_root)
        messages = list(request.get("messages") or [])
        if not shots or not messages:
            return request
        design = [" ".join(str(line).split()) for line in interface_design or () if str(line).strip()]
        note = (
            "\n\n--- How the page looks ---\n"
            "After this text are screenshots of the page as it first loads, before anything "
            "is done on it: " + " and ".join(described for described, _ in shots) + ". "
            + (
                "Judge what a person sees against the interface design in the specification:\n"
                + "\n".join(f"- {line}" for line in design) + "\n"
                if design
                else "Judge what a person sees. "
            )
            + "A page left in the browser's own defaults, content that does not fit the phone's "
            "width, controls that cannot be told apart, or a layout that contradicts the design "
            "is a finding: say which screenshot shows it."
        )
        last = dict(messages[-1])
        text = last.get("content")
        if not isinstance(text, str):
            return request
        last["content"] = [
            {"type": "text", "text": text + note},
            *(
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}}
                for _, data in shots
            ),
        ]
        return {**request, "messages": [*messages[:-1], last]}
    except Exception:  # noqa: BLE001
        return request


__all__ = ["FIXER_NOTE", "MOST_BYTES", "SCREENSHOTS", "with_the_page_for_a_fixer", "with_the_page_screenshots"]
