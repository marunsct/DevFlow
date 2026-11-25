"""A request a model server refuses for its images is sent again without them, and the model is kept as reading none.

Measured on one run: fixers were sent the page's screenshots because the served model's record said it read images
(its model card's task said so), but the server held no vision part for it and answered every request with
``500 - image input is not supported - hint: if this is unexpected, you may need to provide the mmproj``. A 500 looked
like a passing fault, so each request was asked again unchanged until the stage, and then the run, failed.

So an answer that says the server takes no images (that text, and its family: "does not support images", "image
provided but ...", "messages contain images ...") is not asked again as it was: the same request goes once more with
its image parts taken out and its text kept, with one line saying the pictures could not be shown. The server is
remembered for this process, so the rest of the stage's calls - which carry the same pictures in their history - are
sent without them from the start, and `reads_images` is kept as False for the served model
(`app.models.capabilities`), so no later stage attaches any (`app.models.vision`).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

#: What a server says when it refuses a request because it takes no images. Read from the servers' own answers:
#: llama.cpp without a projector ("image input is not supported - hint: ... provide the mmproj"), LM Studio with a
#: text-only file ("Image provided but current GGUF model does not support images"), and others' "does not support
#: image input" / "The provided messages contain images, but ...".
_SAID = re.compile(
    r"image input is not supported|images? (?:input )?(?:is|are) not supported|(?:does|do) not support (?:the )?image"
    r"|doesn'?t support (?:the )?image|image provided but|messages contain images|provide the mmproj"
    r"|not a (?:vision|multimodal) model|no vision (?:support|part|encoder)",
    re.I,
)

#: The part types a message carries an image in: the OpenAI wire form and LangChain's own.
IMAGE_PARTS = frozenset({"image_url", "image", "input_image"})

#: What the model reads where its pictures were taken out.
NOTE = "[The pictures sent with this message could not be shown: this model server takes no images. Work from the text.]"

#: (address, model) of servers that refused a request for its images, in this process.
_TAKES_NO_IMAGES: set[tuple[str, str]] = set()


def says_images_are_refused(error: BaseException) -> bool:
    """Whether `error` is a server refusing a request because it takes no images."""
    chain = [error, *(e for e in (error.__cause__, error.__context__) if e is not None)]
    return any(_SAID.search(str(e) or "") for e in chain)


def _parts(message: Any) -> Any:
    return message.get("content") if isinstance(message, dict) else getattr(message, "content", None)


def _is_an_image(part: Any) -> bool:
    return isinstance(part, dict) and str(part.get("type") or "") in IMAGE_PARTS


def has_images(messages: list[Any]) -> bool:
    """Whether any message carries an image part."""
    return any(isinstance(_parts(m), list) and any(_is_an_image(p) for p in _parts(m)) for m in messages or [])


def without_images(messages: list[Any]) -> list[Any]:
    """`messages` with every image part taken out and its text kept, with `NOTE` where pictures were; a new list."""
    out = []
    for message in messages or []:
        parts = _parts(message)
        if not isinstance(parts, list) or not any(_is_an_image(p) for p in parts):
            out.append(message)
            continue
        kept = [p for p in parts if not _is_an_image(p)]
        texts = [p if isinstance(p, str) else str(p.get("text") or "") for p in kept
                 if isinstance(p, str) or (isinstance(p, dict) and p.get("type") == "text")]
        # Only text is left, so it goes as one string: some servers that take no images take no list either.
        content: Any = "\n\n".join([*(t for t in texts if t), NOTE]) if len(texts) == len(kept) else [
            *kept, {"type": "text", "text": NOTE}]
        if isinstance(message, dict):
            out.append({**message, "content": content})
        else:
            out.append(message.model_copy(update={"content": content}))
    return out


def as_the_server_takes(server: tuple[str, str], messages: list[Any]) -> list[Any]:
    """`messages` without their images when `server` was found to take none; else unchanged."""
    if server in _TAKES_NO_IMAGES and has_images(messages):
        return without_images(messages)
    return messages


def remember(server: tuple[str, str], error: BaseException) -> None:
    """`server` takes no images: kept for this process, and `reads_images` kept False for its model. Never raises."""
    _TAKES_NO_IMAGES.add(server)
    logger.warning("%s refused a request for its images; it is sent none from now on (%s)",
                   server[1] or server[0], str(error)[:160])
    model = server[1]
    try:
        if model:
            from app.models.capabilities import FOUND_KEY, found_values
            from app.models.registry import merge_into_fitness

            merge_into_fitness(model, {FOUND_KEY: {**found_values(model), "reads_images": {
                "value": False, "source": "measured",
                "note": f"a request with an image was refused: {str(error)[:120]}"}}})
    except Exception:  # noqa: BLE001 - the process still remembers it
        logger.debug("Could not keep that the model reads no images", exc_info=True)
    try:
        from app.observability.log_context import current_run
        from app.observability.transcript import record

        run, stage = current_run()
        if run:
            record(run, str(stage or ""), "images_refused", model=model, error=str(error)[:200])
    except Exception:  # noqa: BLE001 - a record must never cost the call
        pass


def forget() -> None:
    """Drop what this process learnt. For tests."""
    _TAKES_NO_IMAGES.clear()


__all__ = ["IMAGE_PARTS", "NOTE", "as_the_server_takes", "forget", "has_images", "remember",
           "says_images_are_refused", "without_images"]
