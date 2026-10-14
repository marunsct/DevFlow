"""The specification written in parts at once, in fast delivery.

Measured on one run: the architect's answer was one reply of 30,000-50,000
tokens - 8 to 14 minutes of a frontier model - and five of them were cut off
before they ended. A cloud model serves several calls side by side.

So the architect, with its research, writes the core: what the release
covers, the components, the contracts, the file plan, the library calls, the
data contracts and its decisions (`CORE`). The other sections are asked for
at once, in `PARTS`, each given the core and the stage's own inputs, and are
joined to it. A part that fails leaves its sections to the existing check for
empty sections, which sends them back to the architect as before.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

#: What the architect writes itself.
CORE = (
    "product_scope", "component_boundaries", "api_and_event_contracts", "file_plan",
    "library_usage", "data_contracts", "decisions",
)
#: The rest, asked for at once, one part per call.
PARTS = (
    ("domain_model", "data_flows", "function_contracts", "implementation_order"),
    ("error_catalogue", "security_and_privacy", "reliability_and_observability", "configuration"),
    ("testing", "test_cases", "acceptance_criteria", "deployment", "interface_design",
     "specialist_advice_decisions", "open_questions"),
)

#: What the architect's request says, in fast delivery.
CORE_NOTE = (
    "\n\nWrite only these sections of the specification: " + ", ".join(CORE) + ". The others - "
    + ", ".join(name for part in PARTS for name in part)
    + " - are written from yours at the same time, so leave them empty; every name, path and "
    "signature they use comes from what you write here.\n"
)


def _described(schema: Any, names: tuple[str, ...]) -> str:
    fields = getattr(schema, "model_fields", {}) or {}
    return "\n".join(
        f"- {name}: {(getattr(fields.get(name), 'description', '') or 'as a technical specification gives it').strip()}"
        for name in names
    )


def part_request(specification: Any, names: tuple[str, ...], context: str) -> str:
    """What one part's call is asked."""
    core = {name: getattr(specification, name, None) for name in CORE}
    return "\n\n".join(part for part in (
        "These are sections of a software product's technical specification. Its core is below, "
        "written by its architect; write the sections named here so they agree with it exactly - "
        "every path, name, signature and message is the one the core gives.",
        context.strip(),
        "--- The specification's core ---\n" + json.dumps(core, indent=1, default=str),
        "--- The sections to write ---\n" + _described(type(specification), names),
        "Reply with one JSON object and nothing else. Its keys are exactly: " + ", ".join(names)
        + ". Each value is a list of strings, one entry per item, each entry complete on its own.",
    ) if part)


def _the_object_in(reply: Any) -> dict[str, Any] | None:
    from app.graph.workflow import _first_json_object
    from app.models.tool_arguments import _parsed_leniently

    text = str(getattr(reply, "content", reply) or "")
    candidate = _first_json_object(text) or text
    try:
        parsed = json.loads(candidate, strict=False)
    except ValueError:
        parsed = _parsed_leniently(candidate)
    return parsed if isinstance(parsed, dict) else None


def with_the_parts_written(specification: Any, model: Any, context: str) -> Any:
    """`specification` with each empty section of `PARTS` written, the parts at once."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.models.tool_arguments import with_structure_decoded

    wanted = [tuple(n for n in part if not getattr(specification, n, None)) for part in PARTS]
    wanted = [part for part in wanted if part]
    if not wanted:
        return specification
    parameters = convert_to_openai_tool(type(specification))["function"]["parameters"]

    def write(names: tuple[str, ...]) -> dict[str, Any]:
        try:
            reply = model.invoke([
                SystemMessage(content="You write sections of software technical specifications as JSON."),
                HumanMessage(content=part_request(specification, names, context)),
            ])
            found = _the_object_in(reply) or {}
            decoded = with_structure_decoded({k: v for k, v in found.items() if k in names}, parameters)
            return {k: v for k, v in decoded.items() if isinstance(v, list) and v}
        except Exception as error:  # noqa: BLE001 - the empty-section check sends them back
            logger.info("A part of the specification (%s) could not be written: %s", ", ".join(names), str(error)[:200])
            return {}

    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        written = list(pool.map(write, wanted))
    update = {k: v for part in written for k, v in part.items()}
    try:
        joined = type(specification).model_validate({**specification.model_dump(), **update})
    except Exception as error:  # noqa: BLE001 - the core stands; the check sends the rest back
        logger.warning("The specification's parts could not be joined to its core: %s", str(error)[:300])
        return specification
    logger.info("Specification parts written at once: %s", ", ".join(sorted(update)) or "none")
    return joined
