"""The reading a specification needs, done before the frontier model is asked to write it.

Measured on one run: the specification stage spent 70 minutes of a frontier
model, most of it reasoning 5,000 to 15,000 tokens before each documentation
read or registry lookup - 2 to 5 minutes to decide which page to read next.
Handing those turns to the build model one at a time did not help: the build
model kept starting on the answer instead.

So the harness does the reading first. It looks every library of the chosen
stack up in its registry itself, asks the build model once which
documentation topics the specification will need, reads those pages itself,
and hands everything to the architect in its request. The architect is then
offered no documentation or registry lookups (`app.tools.research.researched`):
its reasoning goes on the specification.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

#: Documentation pages read before the architect writes.
MOST_TOPICS = 10
#: Characters kept of one page.
MOST_PAGE_CHARACTERS = 3_000
#: Libraries looked up in their registries.
MOST_LIBRARIES = 12

_NOT_A_LIBRARY = re.compile(
    r"^(?:none|n/?a|-|vanilla.*|plain.*|native.*|built-?in.*|html.*|css.*|localstorage|no .*)$", re.I
)


def libraries_of(stack: Any) -> list[str]:
    """The libraries the chosen stack names, each once, in the order the stack gives them."""
    if stack is None:
        return []
    named: list[str] = []
    for field in ("framework", "frontend_framework", "database", "testing_framework"):
        named.append(str(getattr(stack, field, "") or ""))
    named.extend(str(item) for item in getattr(stack, "additional_tools", None) or [])
    found: list[str] = []
    pieces: list[str] = []
    for entry in named:
        # "Hono (on @hono/node-server)": the name, and the one in brackets.
        pieces.append(re.sub(r"\(.*?\)", " ", entry))
        pieces.extend(re.findall(r"\((.*?)\)", entry))
    for entry in pieces:
        for part in re.split(r"\s*(?:,|\+|;|\band\b|\bwith\b|\bon\b|\bvia\b|\bfor\b)\s*", entry):
            name = part.strip().strip(".")
            name = re.sub(r"\s+v?\d[\w.]*$", "", name).strip()
            if " " in name:
                continue
            if name and not _NOT_A_LIBRARY.match(name) and name.lower() not in (f.lower() for f in found):
                found.append(name)
    return found[:MOST_LIBRARIES]


def _topics(libraries: list[str], brief: str, model: Any) -> list[tuple[str, str]]:
    """(library, topic) pairs the specification will need, asked of `model` once."""
    from langchain_core.messages import HumanMessage

    fallback = [(name, "getting started and core API") for name in libraries][:MOST_TOPICS]
    if model is None or not libraries:
        return fallback
    request = (
        "A software product is about to be specified. Its brief and its chosen libraries are below. "
        f"Name the documentation topics (at most {MOST_TOPICS}) its specification needs to get right: "
        "the exact calls, options and behaviours the product depends on.\n\n"
        f"Libraries: {', '.join(libraries)}\n\n--- Brief ---\n{brief[:6000]}\n\n"
        'Reply with one JSON object and nothing else: {"topics": [{"library": "<one of the libraries>", '
        '"topic": "<a few words>"}]}'
    )
    try:
        reply = model.invoke([HumanMessage(content=request)])
        text = str(getattr(reply, "content", reply) or "")
        match = re.search(r"\{.*\}", text, re.S)
        parsed = json.loads(match.group(0)) if match else {}
        known = {name.lower(): name for name in libraries}
        pairs = [
            (known[str(item.get("library", "")).lower()], str(item.get("topic") or "").strip())
            for item in parsed.get("topics") or []
            if isinstance(item, dict) and str(item.get("library", "")).lower() in known and item.get("topic")
        ]
        return pairs[:MOST_TOPICS] or fallback
    except Exception:  # noqa: BLE001 - each library's own overview instead
        logger.info("The build model could not name the documentation topics; reading each library's overview")
        return fallback


def research_notes(stack: Any, brief: str, model: Any, *, workers: int = 6) -> str:
    """The registry versions and documentation the specification needs, as text for its request; "" if nothing was found."""
    from app.tools import docs, package_registry

    libraries = libraries_of(stack)
    if not libraries:
        return ""
    ecosystem = package_registry.ecosystem_named(str(getattr(stack, "language", "") or "")) or ""
    looked_up: list[str] = []
    read: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        if package_registry.enabled() and ecosystem:
            for name, answer in zip(libraries, pool.map(lambda n: _safely(package_registry.look_up, ecosystem, n), libraries)):
                if isinstance(answer, dict) and answer and "error" not in answer:
                    looked_up.append(f"- {name}: " + ", ".join(
                        f"{key}: {value}" for key, value in answer.items() if key not in ("description",)
                    )[:400])
        if docs.enabled():
            topics = _topics(libraries, brief, model)
            pages = pool.map(lambda pair: _safely(docs.read, pair[0], pair[1], ecosystem), topics)
            for (name, topic), answer in zip(topics, pages):
                excerpt = str((answer or {}).get("excerpt") or "") if isinstance(answer, dict) else ""
                if excerpt.strip():
                    read.append(f"### {name}: {topic}\n{excerpt[:MOST_PAGE_CHARACTERS].strip()}")
    if not looked_up and not read:
        return ""
    logger.info("Research done before the architect: %d package(s) looked up, %d page(s) read", len(looked_up), len(read))
    return "\n\n".join(part for part in (
        "--- Research done for this stage: current registry releases and documentation excerpts ---\n"
        "Read for you before this stage, from the registries and the libraries' own documentation. "
        "Write from it; documentation and registry lookups are not offered in this stage.",
        ("Registry releases:\n" + "\n".join(looked_up)) if looked_up else "",
        "\n\n".join(read),
    ) if part) + "\n"


def _safely(function: Any, *args: Any) -> Any:
    try:
        return function(*args)
    except Exception as error:  # noqa: BLE001 - one page that cannot be read leaves the rest
        return {"error": str(error)}
