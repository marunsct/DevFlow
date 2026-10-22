"""A stage's answer asked for in parts when its whole replies keep running out (owner 2026-10-21).

A reasoning model whose reply runs out - reasoning until the limit, or
writing its answer and going on - was answered with the same request again:
thinking switched off (which a model that always reasons ignores), then the
whole stage on a fresh conversation, three times. One run's sprint planner did
that six times at 33,000 tokens a reply and failed the run.

The research says the request is the lever, not the setting: reasoning that
runs longest is reasoning that goes wrong ("Between Underthinking and
Overthinking", arXiv 2505.00127; "Don't Overthink it", arXiv 2505.17813), a
problem broken into smaller ones, each solved with the answers before it, is
solved where the whole is not (least-to-most prompting, Zhou et al., ICLR 2023),
and a structured answer's chance of coming out whole falls with its size. The
harness's own measurement agrees: the specification asked for in three parts
came back in 4,000-15,000 tokens a part, where the whole of it ran out at 33,000.

So the answer is asked for in parts, thinking left as it is, each part a
smaller question: the schema's fields a few at a time, and a field that is a
list of objects one item at a time after a one-line outline of them all. Every
part sees the parts already written, so later ones build on earlier ones. A
part that cannot be read ends the attempt and the stage goes on as before.
"""

from __future__ import annotations

import json
import logging
import typing
from typing import Any

from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

#: Fields asked for in one part.
MOST_FIELDS_PER_PART = 4
#: Items a list is written in, at most.
MOST_ITEMS = 12

_SYSTEM = (
    "You write one part of a structured answer. Answer with that part only: one JSON object "
    "with exactly the fields asked for, nothing before or after it. Keep it as short as the "
    "content allows, and stop when the object is closed."
)


def _item_model(annotation: Any) -> type[BaseModel] | None:
    """The model of a list-of-objects field's items, or None."""
    if typing.get_origin(annotation) is not list:
        return None
    args = typing.get_args(annotation)
    item = args[0] if args else None
    return item if isinstance(item, type) and issubclass(item, BaseModel) else None


def parts_of(schema: Any) -> list[tuple[str, ...]]:
    """The schema's fields in the parts they are asked for in: a list of objects alone, the rest a few at a time."""
    fields = getattr(schema, "model_fields", None) or {}
    parts: list[tuple[str, ...]] = []
    group: list[str] = []
    for name, info in fields.items():
        if _item_model(info.annotation) is not None:
            if group:
                parts.append(tuple(group))
                group = []
            parts.append((name,))
            continue
        group.append(name)
        if len(group) >= MOST_FIELDS_PER_PART:
            parts.append(tuple(group))
            group = []
    if group:
        parts.append(tuple(group))
    return parts


def _part_model(schema: Any, names: tuple[str, ...]) -> type[BaseModel]:
    fields = schema.model_fields
    return create_model(  # type: ignore[call-overload]
        f"{schema.__name__}Part", **{name: (fields[name].annotation, fields[name]) for name in names}
    )


def _read(text: str, model: type[BaseModel]) -> BaseModel | None:
    """The first JSON object in the reply that is `model`, shapes repaired; None when none is.

    Any object, not only the first: measured live, a reply for one item began
    by repeating the parts already written, and the item came after them.
    """
    from app.agents.model_output import strip_reasoning
    from app.agents.settled_answer import validated_leniently
    from app.agents.text_tool_calls import _json_objects
    from app.agents.wrapped_answer import unwrapped

    for candidate in _json_objects(strip_reasoning(text or "")):
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return validated_leniently(model, unwrapped(payload, model))
        except Exception:  # noqa: BLE001 - not this one
            continue
    return None


def _ask(model: Any, request: str, asked: str, shape: type[BaseModel], written: dict[str, Any], stage: str,
         shown: dict[str, Any] | None = None) -> BaseModel | None:
    """One part asked for; asked once more, plainly, if its reply holds no such part.

    `shown` is what of the parts already written this one is shown, when not
    all of it: an item of a list sees the outline and the items before it, and
    only the names of the rest - measured live, an item shown the whole answer
    so far wrote that out again instead of the item.
    """
    for attempt in range(2):
        part = _ask_once(model, request, asked if attempt == 0 else asked + _AGAIN.format(
            fields=", ".join(f"`{name}`" for name in shape.model_fields)), shape, written, stage, shown)
        if part is not None:
            return part
    return None


_AGAIN = (
    " The last reply held no such object. Send only this part: one JSON object whose fields are "
    "{fields}, and nothing else - not the parts already written."
)


def _ask_once(model: Any, request: str, asked: str, shape: type[BaseModel], written: dict[str, Any], stage: str,
              shown: dict[str, Any] | None = None) -> BaseModel | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.observability.direct_calls import config_for_this_run

    seen = written if shown is None else shown
    so_far = (
        "\n\nThe parts already written, which this part goes on from:\n" + json.dumps(seen, indent=1, default=str)
        if seen else ""
    )
    prompt = (
        f"{request}\n\n---\nThe whole answer to the request above ran out of room. It is written in "
        f"parts instead.{so_far}\n\nWrite now: {asked}\n\nThe JSON schema of this part:\n"
        f"{json.dumps(shape.model_json_schema(), indent=1)}"
    )
    try:
        reply = model.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)], **config_for_this_run(stage))
    except Exception:  # noqa: BLE001 - the stage goes on as before
        logger.warning("A part of %s's answer could not be asked for", stage, exc_info=True)
        return None
    content = getattr(reply, "content", "")
    text = content if isinstance(content, str) else "".join(
        block.get("text", "") if isinstance(block, dict) else str(block) for block in content or []
    )
    return _read(text, shape)


def _items(model: Any, request: str, schema: Any, name: str, written: dict[str, Any], stage: str) -> list[Any] | None:
    """A list-of-objects field: an outline of its items, then each item with the ones before it."""
    item = _item_model(schema.model_fields[name].annotation)
    outline_shape = create_model(  # type: ignore[call-overload]
        "Outline", items=(list[str], Field(description=f"One line per item of `{name}`: what that item is.")),
    )
    outline = _ask(model, request, f"the outline of `{name}` - one line per item, nothing more.",
                   outline_shape, written, stage)
    lines = [str(line).strip() for line in getattr(outline, "items", []) or [] if str(line).strip()][:MOST_ITEMS]
    if not lines:
        return None
    items: list[Any] = []
    for index, line in enumerate(lines, 1):
        shown = {"fields already written": sorted(written), f"{name} (outline)": lines,
                 f"{name} (written so far)": [i.model_dump() for i in items]}
        one = _ask(model, request, f"item {index} of {len(lines)} of `{name}`, in full: \"{line}\" - "
                   "one object, this item only.", item, written, stage, shown)
        if one is None:
            return None
        items.append(one)
    return items


def answered_in_parts(schema: Any, request: str, model: Any, stage: str) -> Any | None:
    """The stage's answer, asked for part by part; None when any part cannot be had."""
    if model is None or not isinstance(schema, type) or not issubclass(schema, BaseModel):
        return None
    parts = parts_of(schema)
    if len(parts) < 2 and not any(_item_model(schema.model_fields[n].annotation) for p in parts for n in p):
        return None
    logger.info("Stage %s's whole answer ran out of room; asking for it in %d part(s)", stage, len(parts))
    written: dict[str, Any] = {}
    for names in parts:
        if len(names) == 1 and _item_model(schema.model_fields[names[0]].annotation) is not None:
            items = _items(model, request, schema, names[0], written, stage)
            if items is None:
                logger.warning("Stage %s: the part `%s` could not be written item by item", stage, names[0])
                return None
            written[names[0]] = [i.model_dump() for i in items]
            continue
        part = _ask(model, request, "the fields " + ", ".join(f"`{n}`" for n in names) + ".",
                    _part_model(schema, names), written, stage)
        if part is None:
            logger.warning("Stage %s: the part %s could not be read", stage, ", ".join(names))
            return None
        written.update(part.model_dump())
    try:
        from app.agents.settled_answer import validated_leniently

        answer = validated_leniently(schema, written)
    except Exception:  # noqa: BLE001 - the parts did not make an answer
        logger.warning("Stage %s: the parts did not make an answer the schema accepts", stage, exc_info=True)
        return None
    logger.info("Stage %s answered in %d part(s)", stage, len(parts))
    return answer


__all__ = ["MOST_FIELDS_PER_PART", "MOST_ITEMS", "answered_in_parts", "parts_of"]
