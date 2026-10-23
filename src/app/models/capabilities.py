"""What the serving model can do - set by the owner, else found - kept against the model (owner, 2026-10-23).

Whether a model reads images was guessed from its name, and a name the rules
could not place was taken to read none; whether it reasons, which switch turns
that down, how many languages it answers in, what its makers recommend - each
was a guess somewhere or nowhere at all. Here each is one field of the model's
capability record, and its value comes from, in this order:

1. the owner, on the settings page - always wins;
2. the model server's own account of itself (`/props`: its window, its
   template's tool support, the file and its quantisation);
3. the model, asked (`measure`): a small image whose colour it must name, a
   JSON schema it must answer to, a question in another language - and what
   the tool diagnosis (`diagnostics`) and reply salvage (`reply_salvage`)
   already measured;
4. its model card on Hugging Face (`look_up`): its task, languages, size and
   recommended sampling;

and otherwise it is unknown, which the page shows as missing. A field the
harness acts on is used from here: `reads_images` decides whether reviewers
and fixers are shown the page (`vision.reads_images`).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import struct
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

OWNER_KEY = "capabilities_owner"
FOUND_KEY = "capabilities_found"
LOOKUP_TIMEOUT_SECONDS = 10
PROBE_REPLY_TOKENS = 512


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str  # bool | int | text | choice
    options: tuple[str, ...] = ()


FIELDS: tuple[Field, ...] = (
    Field("reads_images", "Reads images (vision)", "bool"),
    Field("reasons", "Reasons before it answers (thinking)", "bool"),
    Field("thinking_switch", "How its reasoning is turned down", "choice",
          ("none", "chat template", "reasoning effort", "both")),
    Field("native_tool_calls", "Calls tools natively", "bool"),
    Field("forced_tool_enforced", "A required tool call is enforced by the server", "bool"),
    Field("parallel_tool_calls", "Several calls in one reply", "bool"),
    Field("json_schema_answers", "Answers to a JSON schema", "bool"),
    Field("continues_a_begun_reply", "Continues a reply it was given the start of", "bool"),
    Field("multilingual", "Answers in other languages", "bool"),
    Field("languages", "Languages", "text"),
    Field("context_window", "Context window (tokens)", "int"),
    Field("parameters", "Parameters (total / active)", "text"),
    Field("quantisation", "Quantisation", "text"),
    Field("recommended_sampling", "Recommended sampling", "text"),
    Field("model_card", "Model card", "text"),
    Field("think_tag_tokens", "How it opens its reasoning", "text"),
    Field("send_sampling", "Send the recommended sampling with every request", "bool"),
    Field("sampling_to_send", "Sampling to send", "text"),
    Field("dry_sampler", "Use the DRY repetition sampler", "bool"),
)
BY_KEY = {field.key: field for field in FIELDS}
#: Fields only the owner sets: sampling is the owner's (ADR-0008), so nothing
#: found ever turns it on. Off until turned on on the settings page.
OWNER_ONLY = frozenset({"send_sampling", "dry_sampler"})


def _record(model: str) -> dict:
    from app.models.registry import _slug, fitness_dir

    try:
        found = json.loads((fitness_dir() / f"{_slug(model)}.json").read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def owner_values(model: str) -> dict[str, Any]:
    return dict(_record(model).get(OWNER_KEY) or {})


def found_values(model: str) -> dict[str, dict]:
    return dict(_record(model).get(FOUND_KEY) or {})


def set_owner_values(model: str, values: dict[str, Any]) -> None:
    """The owner's values for these keys; None for a key gives it back to what is found."""
    from app.models.registry import merge_into_fitness

    owned = owner_values(model)
    for key, value in values.items():
        if key not in BY_KEY:
            raise KeyError(key)
        if value is None:
            owned.pop(key, None)
        else:
            owned[key] = _as_kind(BY_KEY[key], value)
    merge_into_fitness(model, {OWNER_KEY: owned})


def _as_kind(field: Field, value: Any) -> Any:
    if field.kind == "bool":
        return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    if field.kind == "int":
        return int(value)
    return str(value)


def resolved(model: str) -> list[dict[str, Any]]:
    """Every field: its value, where it came from, why, and the owner's value if any."""
    owned, found = owner_values(model), found_values(model)
    rows = []
    for field in FIELDS:
        if field.key in owned:
            value, source, note = owned[field.key], "owner", "set on the settings page"
        elif field.key in OWNER_ONLY:
            value, source, note = False, "owner", "off until it is turned on here"
        elif field.key in found:
            value, source, note = found[field.key].get("value"), found[field.key].get("source", "measured"), \
                found[field.key].get("note", "")
        else:
            value, source, note = None, "unknown", "not set and not yet found"
        rows.append({"key": field.key, "label": field.label, "kind": field.kind, "options": list(field.options),
                     "value": value, "source": source, "note": note, "owner_value": owned.get(field.key)})
    return rows


def value(model: str, key: str) -> Any:
    """The field's value for `model` - the owner's, else what was found - or None when unknown."""
    owned = owner_values(model)
    if key in owned:
        return owned[key]
    if key in OWNER_ONLY:
        return False
    return (found_values(model).get(key) or {}).get("value")


# --- the reasoning tag, and what may never follow a reasoning prefill --------

#: Tags a chat template may open a reply's reasoning with, most common first.
#: Read from the served template, never assumed of a model.
REASONING_TAGS = ("<think>", "<thinking>", "<reasoning>", "<|begin_of_thought|>", "<|thinking|>")
_TAG_TOKENS = re.compile(r"^(\S+) = (\d+(?:[ ,]+\d+)*)$")


def think_tag_tokens(root: str, headers: dict[str, str], template: str) -> dict | None:
    """The reasoning tag the served template uses and the token ids the server makes of it; None when none. Never raises."""
    tag = next((t for t in REASONING_TAGS if t in (template or "")), "")
    if not tag:
        return None
    try:
        request = urllib.request.Request(
            root + "/tokenize", data=json.dumps({"content": tag, "add_special": False, "parse_special": True}).encode(),
            headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(request, timeout=LOOKUP_TIMEOUT_SECONDS) as reply:
            tokens = json.load(reply).get("tokens") or []
        ids = [int(t["id"] if isinstance(t, dict) else t) for t in tokens]
    except Exception:  # noqa: BLE001 - no tokenizer endpoint: unknown
        return None
    if not ids:
        return None
    note = ("one token, so it can be banned after a reasoning prefill" if len(ids) == 1
            else f"{len(ids)} tokens, so only a stop string can hold it back")
    return _found(f"{tag} = {' '.join(map(str, ids))}", "server", note)


def think_ban(model: str) -> tuple[str, int | None] | None:
    """(the reasoning tag, its one token id or None when it is several) for `model`; None when unknown."""
    found = _TAG_TOKENS.match(str(value(model, "think_tag_tokens") or "").strip())
    if not found:
        return None
    ids = [int(i) for i in re.findall(r"\d+", found.group(2))]
    return found.group(1), (ids[0] if len(ids) == 1 else None)


# --- the owner's sampling, sent with every request -------------------------

#: The DRY sampler's settings when the owner turns it on: the tuned values of
#: the DRY evaluation (multiplier 0.8, base 1.75, allowed length 2; arXiv
#: 2608.22761), over a 1,024-token window - the server's default of 64 is far
#: too short for a long reply.
DRY_MULTIPLIER = 0.8
DRY_BASE = 1.75
DRY_ALLOWED_LENGTH = 2
DRY_PENALTY_LAST_N = 1024
#: The names a sampling line may use: the request field each goes to, and
#: whether the OpenAI request defines it (else it is the server's own field).
_SAMPLING_FIELDS = {
    "temperature": ("temperature", True), "top_p": ("top_p", True),
    "presence_penalty": ("presence_penalty", True), "frequency_penalty": ("frequency_penalty", True),
    "top_k": ("top_k", False), "min_p": ("min_p", False),
    "repetition_penalty": ("repeat_penalty", False), "repeat_penalty": ("repeat_penalty", False),
}
_A_SETTING = re.compile(r"\b([a-z_]+)\s*[=: ]\s*(-?\d+(?:\.\d+)?)", re.I)


def parsed_sampling(text: str) -> dict[str, tuple[str, float, bool]]:
    """`"temperature 0.6, top_k 50"` as {name: (request field, value, an OpenAI field?)}; unknown names left out."""
    out: dict[str, tuple[str, float, bool]] = {}
    for name, number in _A_SETTING.findall(str(text or "")):
        known = _SAMPLING_FIELDS.get(name.lower())
        if known is None:
            continue
        number_value = float(number)
        out[name.lower()] = (known[0], int(number_value) if known[0] == "top_k" else number_value, known[1])
    return out


#: How long a lookup of the owner's sampling is reused: it runs on every request.
SAMPLING_CACHE_SECONDS = 15.0
_SAMPLING_CACHE: dict[str, tuple[float, dict, dict]] = {}


def sampling_for(model_name: str) -> tuple[dict, dict]:
    """(OpenAI fields, the server's own fields) the owner turned on for the serving build model; ({}, {}) otherwise."""
    import time

    # Its own clock, not `monotonic`: a call's pace is measured on that one
    # (`app.models`), and this runs inside every call.
    now = time.perf_counter()
    held = _SAMPLING_CACHE.get(model_name)
    if held and held[0] > now:
        return held[1], held[2]
    top: dict = {}
    extra: dict = {}
    try:
        from app.models.server_profile import current

        # Nothing else is read unless the owner turned something on: this runs
        # in every call, and the settings it would read keep clocks of their own.
        profile = current()
        names = [n for n in ((profile.model if profile is not None else ""), model_name) if n]
        if not any(value(n, "send_sampling") is True or value(n, "dry_sampler") is True for n in names):
            _SAMPLING_CACHE[model_name] = (now + SAMPLING_CACHE_SECONDS, top, extra)
            return top, extra
        from app.models import _runtime_settings
        from app.models.model_guidance import served_now

        if model_name and model_name == str(_runtime_settings().model_name or ""):
            served = served_now() or model_name
            if value(served, "send_sampling") is True:
                for field, number, openai in parsed_sampling(str(value(served, "sampling_to_send") or "")).values():
                    (top if openai else extra)[field] = number
            if value(served, "dry_sampler") is True:
                extra.update({"dry_multiplier": DRY_MULTIPLIER, "dry_base": DRY_BASE,
                              "dry_allowed_length": DRY_ALLOWED_LENGTH, "dry_penalty_last_n": DRY_PENALTY_LAST_N})
    except Exception:  # noqa: BLE001 - nothing sent
        top, extra = {}, {}
    _SAMPLING_CACHE[model_name] = (now + SAMPLING_CACHE_SECONDS, top, extra)
    return top, extra


def with_the_owner_s_sampling(payload: dict, model_name: str) -> dict:
    """`payload` with the sampling the owner turned on for this model; a value the request already has wins."""
    top, extra = sampling_for(model_name)
    for field, number in top.items():
        payload.setdefault(field, number)
    if extra:
        body = dict(payload.get("extra_body") or {})
        for field, number in extra.items():
            if field not in payload:
                body.setdefault(field, number)
        payload["extra_body"] = body
    return payload


def forget_sampling() -> None:
    """Drop the cached lookups. For tests, and after the owner changes a value."""
    _SAMPLING_CACHE.clear()


# --- finding them ------------------------------------------------------------

def _found(value: Any, source: str, note: str) -> dict:
    return {"value": value, "source": source, "note": note}


def from_the_server() -> dict[str, dict]:
    """What the model server says of itself. Never raises."""
    out: dict[str, dict] = {}
    try:
        from app.models.server_profile import current, record

        profile = current() or record()
        if profile is not None:
            if profile.slot_context:
                out["context_window"] = _found(profile.slot_context, "server", "tokens a request gets (/props)")
            if profile.quantisation:
                out["quantisation"] = _found(profile.quantisation, "server", f"from the file {profile.model}")
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the server's profile", exc_info=True)
    try:
        from app.models import _runtime_settings
        from app.models.endpoints import reached_from_here

        settings = _runtime_settings()
        reached, naming = reached_from_here(str(settings.openai_base_url or "").rstrip("/"))
        root = reached[:-3] if reached.endswith("/v1") else reached
        key = str(settings.openai_api_key or "")
        headers = {**({"Authorization": f"Bearer {key}"} if key else {}), **naming}
        with urllib.request.urlopen(urllib.request.Request(root + "/props", headers=headers),
                                    timeout=LOOKUP_TIMEOUT_SECONDS) as reply:
            template = str((json.load(reply) or {}).get("chat_template") or "")
        tag = think_tag_tokens(root, headers, template)
        if tag is not None:
            out["think_tag_tokens"] = tag
    except Exception:  # noqa: BLE001 - a server without /props or /tokenize says nothing
        logger.debug("Could not read the server's reasoning tag", exc_info=True)
    return out


def from_what_was_measured(model: str) -> dict[str, dict]:
    """What the tool diagnosis and reply salvage already found of the model."""
    out: dict[str, dict] = {}
    try:
        from app.models import diagnostics, reply_salvage

        diagnosis = diagnostics.recorded(model)
        if diagnosis is not None:
            by = {c.name: c for c in diagnosis.checks}
            if "tools offered" in by:
                out["native_tool_calls"] = _found(by["tools offered"].works, "measured",
                                                  f"tools offered: {by['tools offered'].passed}/{by['tools offered'].tries}")
            if "two calls in one reply" in by:
                check = by["two calls in one reply"]
                out["parallel_tool_calls"] = _found(check.works, "measured", f"two calls in one reply: {check.passed}/{check.tries}")
            cost = diagnosis.reasoning_tokens or {}
            template = diagnosis.settings.template_thinking_switch
            effort = bool(diagnosis.settings.least_reasoning_effort)
            out["thinking_switch"] = _found(
                "both" if template and effort else "chat template" if template else "reasoning effort" if effort else "none",
                "measured", "which request fields made it reason less")
        support = reply_salvage.recorded(model)
        if support is not None:
            out["continues_a_begun_reply"] = _found(support.salvages, "measured",
                                                    f"reply salvage: {support.shape or 'no shape worked'}")
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the model's measurements", exc_info=True)
    return out


def _png(rgb: tuple[int, int, int], size: int = 32) -> bytes:
    """A solid-colour PNG, made here so nothing is fetched."""
    row = b"\x00" + bytes(rgb) * size
    raw = row * size

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _ask(model: Any, messages: list[dict], **extra: Any) -> tuple[str, str]:
    content, finish, _reasoning = _ask_with_reasoning(model, messages, **extra)
    return content, finish


def _ask_with_reasoning(model: Any, messages: list[dict], **extra: Any) -> tuple[str, str, str]:
    response = model.root_client.chat.completions.create(
        model=model.model_name, messages=messages, max_tokens=PROBE_REPLY_TOKENS, stream=False, **extra)
    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    choice = (data.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    return (str(message.get("content") or ""), str(choice.get("finish_reason") or ""),
            str(message.get("reasoning_content") or message.get("reasoning") or ""))


def measure(model: Any) -> dict[str, dict]:
    """Ask the model what only it can say: an image's colour, an answer to a schema, a reply in Japanese. Never raises."""
    out: dict[str, dict] = {}
    try:
        image = "data:image/png;base64," + base64.b64encode(_png((220, 20, 20))).decode("ascii")
        text, _ = _ask(model, [{"role": "user", "content": [
            {"type": "text", "text": "What colour is this image? Reply with one word."},
            {"type": "image_url", "image_url": {"url": image}}]}])
        out["reads_images"] = _found("red" in text.lower(), "measured",
                                     f"a red square, named {' '.join(text.split())[:30]!r}")
    except Exception as error:  # noqa: BLE001 - a server that refuses an image does not read one
        out["reads_images"] = _found(False, "measured", f"an image was refused: {str(error)[:80]}")
    try:
        # A request no tool answers, with one tool required: a call back means
        # the server enforces `required`. Asked about the weather with the
        # weather tool, a model calls it anyway and forcing looks to work.
        greet = {"type": "function", "function": {"name": "record_greeting", "description": "Record a greeting.",
                 "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}
        response = model.root_client.chat.completions.create(
            model=model.model_name, max_tokens=PROBE_REPLY_TOKENS, stream=False, tools=[greet], tool_choice="required",
            messages=[{"role": "user", "content": "Say hello to me in one word."}])
        data = response if isinstance(response, dict) else response.model_dump(warnings=False)
        calls = ((((data.get("choices") or [{}])[0] or {}).get("message") or {}).get("tool_calls")) or []
        out["forced_tool_enforced"] = _found(bool(calls), "measured", "one tool required for a request it does not fit: "
                                             + ("called it" if calls else "answered in text"))
    except Exception as error:  # noqa: BLE001
        out["forced_tool_enforced"] = _found(False, "measured", f"refused: {str(error)[:80]}")
    try:
        schema = {"type": "object", "properties": {"city": {"type": "string"}, "population": {"type": "integer"}},
                  "required": ["city", "population"], "additionalProperties": False}
        text, _ = _ask(model, [{"role": "user", "content": "Give the capital of France and roughly how many live there."}],
                       response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}})
        parsed = json.loads(text)
        ok = isinstance(parsed, dict) and isinstance(parsed.get("population"), int) and "paris" in str(parsed.get("city", "")).lower()
        out["json_schema_answers"] = _found(ok, "measured", "a two-field schema" + ("" if ok else f": {text[:60]!r}"))
    except Exception as error:  # noqa: BLE001
        out["json_schema_answers"] = _found(False, "measured", f"refused or not JSON: {str(error)[:80]}")
    try:
        # Whether its replies carry reasoning at all: a model that answers a
        # one-number question in 41 tokens can still reason 100,000 on a stage.
        _text, _finish, reasoning = _ask_with_reasoning(model, [{"role": "user", "content":
            "A train leaves at 9:40 and the trip takes 2 hours 35 minutes. When does it arrive? Answer with the time."}])
        out["reasons"] = _found(bool(reasoning.strip()), "measured",
                                f"its reply carried {len(reasoning):,} characters of reasoning")
    except Exception as error:  # noqa: BLE001
        logger.debug("Could not ask whether the model reasons: %s", error)
    try:
        text, _ = _ask(model, [{"role": "user", "content": "日本の首都はどこですか？一文で答えてください。"}])
        japanese = bool(re.search(r"[぀-ヿ一-鿿]", text)) and ("東京" in text)
        out["multilingual"] = _found(japanese, "measured", "asked in Japanese" + (", answered in Japanese" if japanese else
                                                                                  f": {' '.join(text.split())[:40]!r}"))
    except Exception as error:  # noqa: BLE001
        out["multilingual"] = _found(False, "measured", f"no answer: {str(error)[:80]}")
    return out


def _get(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "harness-capabilities"})
    with urllib.request.urlopen(request, timeout=LOOKUP_TIMEOUT_SECONDS) as reply:
        body = reply.read()
    return json.loads(body) if url.endswith(tuple(("json",))) or "/api/" in url else body.decode("utf-8", "replace")


def _the_repo(name: str) -> str:
    """The Hugging Face repository a served or configured name most likely is; "" when none is found."""
    clean = re.sub(r"(?:-\d{5}-of-\d{5})?\.gguf$", "", name.strip(), flags=re.I)
    if "/" in clean:
        return clean
    query = re.sub(r"[-_](?:i?q\d[\w]*|f16|bf16|gguf)$", "", clean, flags=re.I)
    found = _get("https://huggingface.co/api/models?" + urllib.parse.urlencode({"search": query, "limit": 5}))
    return str(found[0].get("id") or "") if isinstance(found, list) and found else ""


_SIZE = re.compile(r"(\d+(?:\.\d+)?)B(?:[-_ ]?A(\d+(?:\.\d+)?)B)?", re.I)
_SAMPLING = re.compile(r"\b(temperature|top_p|top_k|min_p|repetition_penalty|presence_penalty)\s*[=:]\s*(\d+(?:\.\d+)?)", re.I)


def look_up(names: list[str]) -> dict[str, dict]:
    """The model card on Hugging Face of the first name that resolves to a repository. Never raises."""
    out: dict[str, dict] = {}
    for name in [n for n in names if n]:
        size = _SIZE.search(name)
        if size and "parameters" not in out:
            out["parameters"] = _found(f"{size.group(1)}B" + (f" total / {size.group(2)}B active" if size.group(2) else ""),
                                       "model card", f"from its name {name}")
        try:
            repo = _the_repo(name)
            if not repo:
                continue
            info = _get(f"https://huggingface.co/api/models/{repo}")
            card = info.get("cardData") or {}
            out["model_card"] = _found(f"https://huggingface.co/{repo}", "model card", "the repository its name resolves to")
            task = str(info.get("pipeline_tag") or "")
            if task:
                out["reads_images"] = _found(task in ("image-text-to-text", "visual-question-answering", "image-to-text"),
                                             "model card", f"its task is {task}")
            languages = card.get("language") or []
            languages = [languages] if isinstance(languages, str) else languages
            if languages:
                out["languages"] = _found(", ".join(map(str, languages))[:200], "model card", "the card's language list")
                out["multilingual"] = _found(len(languages) > 1, "model card", f"{len(languages)} language(s) listed")
            total = ((info.get("gguf") or {}).get("total")) or ((info.get("safetensors") or {}).get("total"))
            if total:
                out["parameters"] = _found(f"{total / 1e9:.1f}B" + (f" ({out['parameters']['value']})" if "parameters" in out else ""),
                                           "model card", "the repository's weights")
            try:
                readme = _get(f"https://huggingface.co/{repo}/raw/main/README.md")
                sampling = dict((k.lower(), v) for k, v in _SAMPLING.findall(readme))
                if sampling:
                    out["recommended_sampling"] = _found(", ".join(f"{k} {v}" for k, v in sampling.items()),
                                                         "model card", "from the card's text")
            except Exception:  # noqa: BLE001 - the card's text is optional
                pass
            break
        except Exception:  # noqa: BLE001 - no card is an unknown, not a failure
            logger.debug("Could not look the model up", exc_info=True)
    return out


def fill(model: Any, name: str, configured: str = "") -> dict[str, dict]:
    """Find every field not set by the owner, measured over looked-up over the server's; keep it. Never raises."""
    from app.models.registry import merge_into_fitness

    found: dict[str, dict] = {}
    for source in (look_up([configured, name]), from_the_server(), from_what_was_measured(name), measure(model)):
        found.update(source)  # later, more direct sources win
    if "recommended_sampling" in found:
        # What would be sent, should the owner turn sampling on; the owner may edit it.
        found["sampling_to_send"] = _found(found["recommended_sampling"]["value"], found["recommended_sampling"]["source"],
                                           "the recommended sampling; sent only once it is turned on")
    found["_at"] = {"value": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": "measured", "note": ""}
    merge_into_fitness(name, {FOUND_KEY: found})
    return found


__all__ = ["BY_KEY", "DRY_ALLOWED_LENGTH", "DRY_BASE", "DRY_MULTIPLIER", "DRY_PENALTY_LAST_N", "FIELDS", "Field",
           "OWNER_ONLY", "REASONING_TAGS", "fill", "forget_sampling", "found_values", "from_the_server",
           "from_what_was_measured", "look_up", "measure", "owner_values", "parsed_sampling", "resolved", "sampling_for",
           "set_owner_values", "think_ban", "think_tag_tokens", "value", "with_the_owner_s_sampling"]
