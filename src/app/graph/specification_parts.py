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

import re

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

#: The sections written in parts that fix the names writers use.
NAMING_SECTIONS = frozenset({"function_contracts", "error_catalogue", "implementation_order"})

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


#: The sections that give the acceptance criteria their ids; a part writing neither cannot see them.
_CRITERIA_SECTIONS = frozenset({"acceptance_criteria", "interface_contract"})
#: Said to every other part. Measured on one run: `implementation_order` cited AC ids while another part wrote the
#: criteria at the same time, every step pointed at the wrong one, and the design review sent it all back.
CITE_NO_CRITERION = (
    "The acceptance criteria and the interface contract are being written at the same time as these sections, "
    "so the ids they add are not known here: cite an AC-n id only where the material above already gives it. "
    "Otherwise name the behaviour itself - "
    "the endpoint, file, function or rule - and the criteria will point at it."
)


def _one_source_for_limits() -> str:
    from app.agents.principal_architect import ONE_SOURCE_FOR_LIMITS

    return ONE_SOURCE_FOR_LIMITS.strip()


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
        "" if _CRITERIA_SECTIONS & set(names) else CITE_NO_CRITERION,
        # The architect's own rule for limits: the part writers write `domain_model` and the sections that cite it.
        _one_source_for_limits(),
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
        written = ask(names)
        # A section that fixes names and came back empty is asked for once more (NAMING_STANDARD): the writers
        # downstream take their names from it, and "Not specified" left each to invent its own.
        from app.stacks.naming import enabled

        missing = tuple(n for n in names if n in NAMING_SECTIONS and n not in written) if enabled() else ()
        if missing:
            logger.info("Asking again for the specification sections %s", ", ".join(missing))
            written = {**written, **ask(missing)}
        return written

    def ask(names: tuple[str, ...]) -> dict[str, Any]:
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


#: How a repair the harness writes names what it wants back: "Return only `testing` ...".
_RETURN_ONLY = re.compile(r"Return only (?:the missing fields: )?(.+?)(?:[.;]\s|[.;]$|$)", re.DOTALL)


def sections_the_harness_named(specification: Any, required_changes: str) -> list[str]:
    """The sections a harness-made repair names, when every part of `required_changes` is one; else [].

    A review's own findings name no section this way, so a text with any part that is not a harness repair is asked
    of the model as before, its named sections included.
    """
    names = _names(specification)
    parts = [part for part in re.split(r"\n\s*\n", required_changes) if part.strip()]
    chosen: list[str] = []
    for part in parts:
        found = _RETURN_ONLY.search(part)
        if not found:
            return []
        named = [name for name in names if re.search(rf"\b{re.escape(name)}\b", found.group(1))]
        if not named:
            return []
        chosen.extend(name for name in named if name not in chosen)
    return chosen


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


#: What a review calls a section other than its name: an architecture decision record is "ADR-6", and the
#: specification keeps those in `decisions`. Measured on one run: a finding about ADR-06's counts was the only one a
#: revision left unfixed - the section was never chosen to be rewritten - and the run escalated on it.
_SECTION_CALLED = {"decisions": re.compile(r"\badrs?\b(?:[\s-]*\d+)?", re.I)}


def named_in(name: str, text: str) -> bool:
    """Whether `text` names the section `name`: as written, in words, or as reviews call it (`_SECTION_CALLED`)."""
    lowered = (text or "").lower()
    spaced = lowered.replace("-", " ")
    called = _SECTION_CALLED.get(name)
    return (name.lower() in lowered or name.replace("_", " ").lower() in spaced
            or bool(called is not None and called.search(text or "")))


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
    named = [name for name in names if named_in(name, required_changes)]
    if not named:
        return chosen
    extra = [name for name in chosen if name not in named][:MOST_UNNAMED_SECTIONS]
    return [*[name for name in chosen if name in named], *[n for n in named if n not in chosen], *extra]


#: Where one finding of the required changes begins: "- [blocking] ...", "- [major] ...".
_A_FINDING = re.compile(r"\n(?=\s*-\s*\[)")


def grouped_by_finding(chosen: list[str], required_changes: str) -> list[tuple[str, ...]]:
    """`chosen` in groups of at most `SECTIONS_PER_REVISION`, the sections one finding names always in one group.

    Each group is rewritten by its own call, at once, blind to the others' new text. Measured on one run: a finding
    said `file_plan` declares `create_app(storage)` while `function_contracts` declares `create_app()`; the two fell
    in different groups, each was rewritten alone, and the second review raised the same contradiction word for word.
    A set of sections findings tie together larger than a group is one group.
    """
    parent = {name: name for name in chosen}

    def root(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for finding in _A_FINDING.split(required_changes or ""):
        named = [name for name in chosen if named_in(name, finding)]
        for other in named[1:]:
            parent[root(other)] = root(named[0])
    tied: dict[str, list[str]] = {}
    for name in chosen:
        tied.setdefault(root(name), []).append(name)
    groups: list[list[str]] = []
    for members in tied.values():
        last = groups[-1] if groups else None
        if last is not None and len(last) + len(members) <= SECTIONS_PER_REVISION:
            last.extend(members)
        else:
            groups.append(list(members))
    return [tuple(group) for group in groups]


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
    # A repair the harness made names its sections itself (HR2.D.2): 251 of 357 rounds were such repairs, each still
    # asked of the model ("Name every section ..."), whose answer was then mostly bounded away.
    chosen = sections_the_harness_named(specification, required_changes) or sections_to_revise(
        specification, required_changes, model)
    if not chosen:
        # Not a reason to hand the whole document back to one reply. Measured
        # live on a medium brief: the architect's full rewrite was cut at the
        # 20,000-token output cap three times running, two and a half minutes
        # each. Every section, a few at a time, fits where one reply does not.
        logger.info("Could not tell which sections the review's changes touch; revising every section in parts")
        chosen = _names(specification)
    groups = grouped_by_finding(chosen, required_changes)
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
