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

from app.observability.direct_calls import config_for_this_run, mapped_in_this_context

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
     "interface_contract", "specialist_advice_decisions", "open_questions"),
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


def _sections_as_json(specification: Any, names: Any) -> dict[str, Any]:
    """The named sections as the specification's own JSON.

    Measured live: shown through `json.dumps(..., default=str)`, each decision
    record arrived as `title='...' decision='...'`; the reviser handed them back
    so, and the revision - five minutes of model time - could not be joined
    ("11 validation errors") and was thrown away.
    """
    try:
        dumped = specification.model_dump(mode="json")
    except Exception:  # noqa: BLE001 - a plain object: its attributes as they are
        dumped = {}
    return {name: dumped.get(name, getattr(specification, name, None)) for name in names}


def part_request(specification: Any, names: tuple[str, ...], context: str) -> str:
    """What one part's call is asked."""
    core = _sections_as_json(specification, CORE)
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
    if not text.strip():
        reasoning = (getattr(reply, "additional_kwargs", {}) or {}).get("reasoning_content") or ""
        if isinstance(reasoning, str) and reasoning.strip():
            text = reasoning
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
    if model is None:
        # No model named: the stages build the deployment's own, and so does
        # this. One run on the build model only handed `None` here and every
        # part failed on `None.invoke`, so the architect wrote them all again.
        from app.models import build_default_chat_model

        model = build_default_chat_model()
    from app.agents.thinking import without_reasoning

    call_model = without_reasoning(model)
    parameters = convert_to_openai_tool(type(specification))["function"]["parameters"]

    def write(names: tuple[str, ...]) -> dict[str, Any]:
        try:
            messages = [
                SystemMessage(content="You write sections of software technical specifications as JSON."),
                HumanMessage(content=part_request(specification, names, context)),
            ]
            reply = call_model.invoke(messages, **config_for_this_run("principal_architect"))
            found = _the_object_in(reply) or {}
            decoded = with_structure_decoded({k: v for k, v in found.items() if k in names}, parameters)
            written = {k: v for k, v in decoded.items() if isinstance(v, list) and v}
            if len(written) < len(names):
                text = str(getattr(reply, "content", reply) or "")
                logger.info(
                    "A part of the specification (%s) came back without %s: %d characters of reply, beginning %r",
                    ", ".join(names), ", ".join(n for n in names if n not in written) or "nothing",
                    len(text), text[:160],
                )
            return written
        except Exception as error:  # noqa: BLE001 - the empty-section check sends them back
            logger.info("A part of the specification (%s) could not be written: %s", ", ".join(names), str(error)[:200])
            return {}

    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        written = mapped_in_this_context(pool, write, wanted)
    update = {k: v for part in written for k, v in part.items()}
    try:
        joined = type(specification).model_validate({**specification.model_dump(), **update})
    except Exception as error:  # noqa: BLE001 - the core stands; the check sends the rest back
        logger.warning("The specification's parts could not be joined to its core: %s", str(error)[:300])
        return specification
    logger.info("Specification parts written at once: %s", ", ".join(sorted(update)) or "none")
    return joined


# --- a revision, made in place ----------------------------------------------------
#
# Measured on one run: sent back once, the architect was handed its previous
# specification - 144,000 of the request's 230,000 characters - and wrote all
# of it again: one reply of 47,669 tokens over 10 minutes, and on the next
# visit one cut off after 103,080 characters. The review named a handful of
# sections. So in fast delivery a revision asks which sections the required
# changes touch and rewrites only those, at once, keeping the rest as they were.

#: Sections one revising call rewrites.
SECTIONS_PER_REVISION = 3


def _names(specification: Any) -> list[str]:
    return list(getattr(type(specification), "model_fields", {}) or {})


def sections_to_revise(specification: Any, required_changes: str, model: Any) -> list[str]:
    """The sections the required changes touch, asked of `model` once; [] if it cannot say."""
    from langchain_core.messages import HumanMessage

    names = _names(specification)
    request = (
        "A software product's technical specification was reviewed and must change as below. Name every "
        "section that has to be rewritten to make these changes - and any other section that repeats "
        "a name, path, signature or message being changed, so the specification stays consistent.\n\n"
        f"--- Required changes ---\n{required_changes.strip()[:20_000]}\n\n"
        f"--- The sections ---\n{_described(type(specification), tuple(names))}\n\n"
        'Reply with one JSON object and nothing else: {"sections": ["<section name>", ...]}'
    )
    try:
        found = _the_object_in(model.invoke(
            [HumanMessage(content=request)], **config_for_this_run("principal_architect"),
        )) or {}
    except Exception as error:  # noqa: BLE001 - the architect revises as before
        logger.info("Could not tell which sections a revision touches: %s", str(error)[:200])
        return []
    chosen = list(dict.fromkeys(str(name) for name in found.get("sections") or [] if str(name) in names))
    return _bounded_by_what_the_review_names(chosen, required_changes, names)


#: Sections a revision rewrites beyond those the review's own words name.
MOST_UNNAMED_SECTIONS = 2


def _bounded_by_what_the_review_names(chosen: list[str], required_changes: str, names: list[str]) -> list[str]:
    """`chosen` kept to the sections the required changes name, and at most a few more.

    Asked for every section the changes touch and every one that repeats a
    changed name, the model named nearly all of them. Measured on the first
    all-on run: three review rounds of three blocking findings each, every
    revision rewriting ten sections at 4,000-14,000 tokens apiece - 56 of the
    architect's model minutes. The review cites the sections it means
    ("Function contracts section line 147", "Configuration section").
    """
    text = (required_changes or "").lower().replace("-", " ")
    named = [name for name in names if name.replace("_", " ").lower() in text]
    if not named:
        return chosen
    extra = [name for name in chosen if name not in named][:MOST_UNNAMED_SECTIONS]
    return [*[name for name in chosen if name in named], *[n for n in named if n not in chosen], *extra]


def _the_form_of(parameters: dict[str, Any], names: Any) -> str:
    """The schema of the named sections, so a section that holds nothing yet still has a form to be written in.

    Measured: a section that was an empty list was rewritten with record keys
    of the reply's own (`summary` for `context` and `decision`), since the
    "form of the current value" was none - nine validation errors, and the
    revision thrown away.
    """
    properties = (parameters or {}).get("properties") or {}
    form = {name: properties[name] for name in names if name in properties}
    return "--- The form of each section (JSON schema) ---\n" + json.dumps(form, default=str) if form else ""


def revised_in_place(specification: Any, required_changes: str, model: Any, context: str) -> Any | None:
    """`specification` with only the sections the changes touch rewritten, or None to revise as before."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.models.tool_arguments import with_structure_decoded

    if model is None or not required_changes.strip():
        return None
    chosen = sections_to_revise(specification, required_changes, model)
    if not chosen:
        # Not a reason to hand the whole document back to one reply. Measured
        # live on a medium brief: the architect's full rewrite was cut at the
        # 20,000-token output cap three times running, two and a half minutes
        # each. Every section, a few at a time, fits where one reply does not.
        logger.info("Could not tell which sections the review's changes touch; revising every section in parts")
        chosen = _names(specification)
    groups = [tuple(chosen[n:n + SECTIONS_PER_REVISION]) for n in range(0, len(chosen), SECTIONS_PER_REVISION)]
    parameters = convert_to_openai_tool(type(specification))["function"]["parameters"]
    core = _sections_as_json(specification, CORE)

    def revise(names: tuple[str, ...]) -> dict[str, Any] | None:
        current = _sections_as_json(specification, names)
        request = "\n\n".join(part for part in (
            "A software product's technical specification was reviewed. Rewrite the sections below so "
            "they make the required changes, change nothing else in them, and agree with the rest of "
            "the specification exactly - every path, name, signature and message.",
            context.strip(),
            f"--- Required changes ---\n{required_changes.strip()[:20_000]}",
            "--- The specification's core, as it stands ---\n" + json.dumps(core, indent=1, default=str),
            _the_form_of(parameters, names),
            "--- The sections to rewrite, as they stand ---\n" + json.dumps(current, indent=1, default=str),
            "Reply with one JSON object and nothing else. Its keys are exactly: " + ", ".join(names)
            + ". Each value has the form its schema gives, whatever the section holds now.",
        ) if part)
        try:
            reply = model.invoke([
                SystemMessage(content="You revise sections of software technical specifications as JSON."),
                HumanMessage(content=request),
            ], **config_for_this_run("principal_architect"))
            found = _the_object_in(reply) or {}
            decoded = with_structure_decoded({k: v for k, v in found.items() if k in names}, parameters)
            written = {k: v for k, v in decoded.items() if v not in (None, "", [], {})}
            # A section answered with an empty value is a section left as it
            # stands: measured, a reply wrote the one section the changes
            # touched and answered an empty list for a second that held none,
            # and the nine minutes it took were thrown away for a full rewrite.
            for name in names:
                if name not in written and name in decoded and decoded[name] is not None and not decoded[name] and name in current:
                    written[name] = current[name]
            if len(written) < len(names):
                logger.info("A revision of %s came back without %s", ", ".join(names),
                            ", ".join(n for n in names if n not in written))
                return None
            return written
        except Exception as error:  # noqa: BLE001 - the architect revises as before
            logger.info("A revision of %s could not be written: %s", ", ".join(names), str(error)[:200])
            return None

    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        written = mapped_in_this_context(pool, revise, groups)
    if any(part is None for part in written):
        return None
    update = {k: v for part in written for k, v in part.items()}
    try:
        revised = type(specification).model_validate({**specification.model_dump(), **update})
    except Exception as error:  # noqa: BLE001 - the architect revises as before
        logger.warning("A revision made in place could not be joined: %s", str(error)[:300])
        return None
    logger.info("Specification revised in place: %s", ", ".join(chosen))
    return revised
