# Implementation Plan — Context Compaction

**Status:** ready to execute
**Audience:** an implementing agent. Every anchor string in this document was copied from the current source. Every API signature was read from the installed package, not from memory.
**Scope:** keep long agent runs inside the model's context window without losing work.
**Constraint:** do not weaken the existing security model. Where a step could, the plan says so explicitly and routes around it.

---

## Part 0 — Review of the previous plan

The previous draft was reviewed against the running system. It is directionally right — threshold-triggered summarisation plus offloading plus tool-output truncation is the correct shape — but seven items would fail at runtime. Each was verified, not inferred.

### 0.1 `SummarizationMiddleware` takes none of the arguments used

The draft called:

```python
SummarizationMiddleware(
    summarization_model=compaction_model,
    max_tokens=policy.max_context_tokens * policy.soft_trigger_ratio,
    min_history=policy.min_history_for_compact,
    min_delta=policy.min_delta_since_last,
)
```

The installed signature is:

```
SummarizationMiddleware(
    model: str | BaseChatModel,
    *,
    backend: BackendProtocol,                     # REQUIRED keyword
    trigger: ContextSize | TriggerClause | list[...] | None = None,
    keep: ContextSize = ('messages', 20),
    token_counter: TokenCounter = count_tokens_approximately,
    summary_prompt: str = <a long default prompt>,
    trim_tokens_to_summarize: int | None = 4000,
    truncate_args_settings: TruncateArgsSettings | None = None,
)
```

`summarization_model`, `max_tokens`, `min_history` and `min_delta` do not exist. The call raises `TypeError` on the first agent construction, which means **every stage of every run fails immediately**. `backend` is required and the draft never passes it.

`ContextSize` is a tuple union:

```
tuple[Literal['fraction'], float] | tuple[Literal['tokens'], int] | tuple[Literal['messages'], int]
```

So a threshold is written `("fraction", 0.8)` or `("tokens", 60000)` — not a bare number.

### 0.2 `BackendProtocol` is a filesystem, not a key-value store

The draft's `OffloadBackend` implements `save(key, value)` and `load(key)`. The actual protocol is:

```
read  write  edit  ls  glob  grep  delete  upload_files  download_files
aread awrite aedit als aglob agrep adelete aupload_files adownload_files
```

Neither `save` nor `load` is in it. The object would not satisfy the protocol, and `SummarizationMiddleware` would call `read`/`write` on it and raise `AttributeError`.

The package already ships `FilesystemBackend`, `StateBackend`, `StoreBackend`, `CompositeBackend` and `ContextHubBackend`. Writing a new one by hand is unnecessary and is why the interface was guessed wrong.

### 0.3 The settings lookup silently reads nothing

`ContextPolicy.from_settings()` does:

```python
env = overrides()
max_context_tokens=int(env.get("CTX_MAX_TOKENS", 75000))
```

`runtime_settings.overrides()` returns rows keyed by **setting name**, filtered to `SETTABLE_KEYS`:

```python
return {key: value for key, value in rows if key in SETTABLE_KEYS}
```

Adding `"context_max_tokens": "CTX_MAX_TOKENS"` to `SETTABLE_KEYS` makes the returned key `context_max_tokens`. Looking up `CTX_MAX_TOKENS` therefore **always misses and always returns the default**. Every threshold would be silently unconfigurable — the worst kind of failure, because it looks like it works.

There is a second problem behind it: `SETTABLE_KEYS` is also what the settings API writes through, and `SettingsUpdate` is a fixed Pydantic model with three fields. Adding six keys to `SETTABLE_KEYS` without touching the API leaves them writable by nothing.

### 0.4 The overflow guard kills the run it is meant to save

The draft returns:

```python
return {"error": "ContextOverflowError", "stage": stage}
```

Two faults. `stage` is not a variable in `_run_gated_agent`; the parameter is `stage_name`, so this raises `NameError`. And even corrected, `"ContextOverflowError"` is not a node:

```
is ContextOverflowError a node? False
router would return: ContextOverflowError
-> edge map lookup would KeyError, killing the run
```

`_route_from_stage` returns the stage verbatim and the conditional-edge map is built from `_NODE_NAMES`, so an unknown name is a `KeyError`. This is the same defect class as the historical `sprint_advance` bug: a stage that exists in code but not in the routing table.

### 0.5 The anchor for that edit does not exist

The draft says to find `result = agent.invoke(agent_state, config)`. The real code has two invoke sites and neither matches:

```
352:  result = resume_with_decision(agent, inner_thread_id, pending_decision)
373:  result = agent.invoke(initial_request, config={"configurable": {"thread_id": inner_thread_id}})
```

A find-and-replace would not match at all. Worse, the draft only guards one path — the resume path at 352 is exactly where a long, already-summarised conversation is restored, so it is *more* likely to overflow, not less.

### 0.6 Phase 5 targets a function that does not exist

`src/app/server/uploads.py` contains `validate_and_store`, `ensure_upload_dir`, `extension_of`, `_safe_stem`, `_content_type_for`. There is no `process_upload`. The phase is also self-contradictory — it says to restructure document parsing and then says not to.

### 0.7 The compaction model default cannot work here

`ChatOpenAI(model="gpt-4o-mini", temperature=0.0)` is constructed with no `base_url` and no `api_key`, so it targets `api.openai.com`. This deployment serves a local model at an OpenAI-compatible endpoint. Every compaction attempt would 401.

It also bypasses `CompatibleChatOpenAI`, which exists because this server rejects `name` on non-tool messages — so even with credentials it would 400.

### 0.8 What the draft did not cover at all

- **No tests.** Nothing verifies compaction triggers, preserves the structured output, or survives an approval pause.
- **The largest measured context cost is not message history.** See Part 1.
- **Interaction with approval/resume.** Agents pause mid-conversation and resume from a checkpoint; a summarised history must survive that round trip.
- **Interaction with fresh-inner-thread-per-attempt.** `_run_gated_agent` already mints a new thread id per attempt specifically to discard history.
- **Artifact pollution.** Journal and offload directories inside the workspace would be listed as run artifacts and archived to object storage.

---

## Part 1 — The problem, measured

Do not skip this. It determines which phases matter.

### 1.1 Oversized first request (the dominant cost today)

Measured on a real run of this system, seven uploaded documents totalling 135,821 characters:

| Request | Size | Share that is raw documents |
|---|---|---|
| Architect, first attempt | ~35,200 tokens | 96% |
| Architect, each revision | ~37,600 tokens | 90% |

The architect receives `product_intake` — the product manager's distillation of those documents — **and** the full corpus again beside it. Revisions add the previous specification and the reviewer's findings on top, so the request grows rather than shrinks.

**Summarisation middleware does nothing about this.** It compacts *conversation history*; this is a single oversized first message. It needs a request budget, which is Phase 5.

A partial mitigation already exists: `build_architecture_revision_request` trims to `REVISION_DOCUMENT_BUDGET = 20_000` characters. The first request is untouched.

### 1.2 Long tool loops (the cost that is about to grow)

Command execution was recently enabled (`ALLOW_COMMAND_EXECUTION=true`, `SANDBOX_EXECUTION_MODE=in-container`). Specialists now run `npm install`, compile, read errors, fix, recompile. Each cycle appends a tool call and its output to the inner agent's history. This is exactly what summarisation is for, and it is why this work is needed now rather than later.

### 1.3 Tool output size

`SandboxExecutor` already truncates combined output at `MAX_OUTPUT_SIZE = 50 * 1024` bytes (~12.5k tokens) per call, appending `...[truncated, exceeded N bytes]`. The cap exists; what is missing is that the discarded remainder is simply lost. A journal fixes that without adding a second truncation layer.

### 1.4 Where the ceilings currently are

| Setting | Value | File |
|---|---|---|
| `MAX_OUTPUT_SIZE` | 50 KB | `src/app/tools/sandbox.py` |
| `REVISION_DOCUMENT_BUDGET` | 20,000 chars | `src/app/agents/principal_architect.py` |
| `max_text_chars` | 250,000 chars | `src/app/documents.py` |
| `DEFAULT_RECURSION_LIMIT` | 100 | `src/app/graph/workflow.py` |
| `MAX_GATES` | 1000 | `src/app/server/runner.py` |

---

## Part 2 — Design decisions

Read these before writing code; they explain why later steps look the way they do.

### D1. The agent's backend stays `StateBackend`

`create_deep_agent(backend=...)` is **not** set. It stays at its default.

Why this matters: `role_agent.py` currently denies the built-in filesystem tools outright —

```python
permissions=[
    FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny"),
],
```

— because the default backend is an in-memory `StateBackend`, not the real repository. Every real write goes through `write_artifact`, which is approval-gated and workspace-contained.

Pointing the agent's backend at a `FilesystemBackend` rooted in the workspace would re-enable those built-in tools against real files and hand agents an **ungated write path**, bypassing the approval gate entirely. Do not do it.

`SummarizationMiddleware` takes its **own** `backend` argument, separate from the agent's. That is the one to set.

### D2. The middleware's backend is a filesystem rooted outside the workspace

Summaries and offloaded content must not land in the run workspace, because the workspace is:
- listed as run artifacts (`_collect_artifacts` → `list_repository_files`),
- archived to object storage on terminal states (`archive_directory`),
- shown to the user in the artifact viewer.

Put context data under `DATA_DIR/context/<thread_id>/` instead. It is per-run, inspectable, and outside everything that treats the workspace as product output.

### D3. Compaction uses the run's own model by default

Never hardcode `gpt-4o-mini`. Build the compaction model through `app.models.build_default_chat_model`, which resolves provider, base URL, model name and credentials from effective settings and returns `CompatibleChatOpenAI` (which strips `name` from non-tool messages — required by this deployment's server).

An override is allowed via `CTX_COMPACTION_MODEL`, but when set it must still be built through the same factory so it inherits base URL and credentials.

### D4. Configuration is read from the effective environment

Use `runtime_settings.effective_environment()`, which returns `os.environ` with database-stored overrides layered on top, **keyed by environment variable name**. This makes `CTX_*` variables work from `.env`, from compose, and from a future settings-API exposure, without the key-name mismatch that broke the draft.

Do **not** add the `CTX_*` keys to `SETTABLE_KEYS` in this phase. `SETTABLE_KEYS` is coupled to the settings API's fixed `SettingsUpdate` model; adding keys there without extending that model produces settings nothing can write. Exposing them in the UI is a separate, optional phase (Phase 7).

### D5. Overflow returns a real stage

The only safe values for `stage` are members of `_NODE_NAMES`. On unrecoverable overflow, return `"failed"` with a readable `error`. `failed` is a real node and the runner already records, publishes and closes the run correctly for it.

### D6. Both invoke paths are guarded

`_run_gated_agent` has two, and the resume path is the more likely to overflow because it restores an accumulated conversation.

---

## Part 3 — Implementation

Work in order. After each step, run the stated verification. If a verification fails, stop and fix before continuing.

Assume the repository root is `/home/arun/Desktop/langchain` and that commands run from there with `PYTHONPATH=src`.

---

### Phase 1 — Context policy

#### Step 1.1 — Create `src/app/agents/context_policy.py`

Create the file with exactly this content:

```python
"""Thresholds that keep an agent's conversation inside the model's window.

Read from the effective environment - the deployed environment plus any
override an administrator has stored - so a value can be changed without a
rebuild. Every field has a default that works unconfigured.

Deliberately not wired into `SETTABLE_KEYS`: that map is what the settings API
writes through, and its request model has a fixed set of fields. Adding keys
there without extending that model would produce settings nothing can write.
"""

from __future__ import annotations

import logging
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ContextPolicy(BaseModel):
    """How much context an agent may use, and when to compact it."""

    model_config = ConfigDict(extra="forbid")

    max_context_tokens: int = Field(
        default=75_000,
        description="The model's usable input window, in tokens.",
    )
    soft_trigger_ratio: float = Field(
        default=0.8,
        ge=0.1,
        le=0.95,
        description="Fraction of the window at which compaction runs.",
    )
    keep_recent_messages: int = Field(
        default=20,
        ge=2,
        description="Messages left untouched at the tail when compacting.",
    )
    trim_tokens_to_summarize: int = Field(
        default=4_000,
        ge=500,
        description="Token budget the summariser itself may spend.",
    )
    compaction_model: str = Field(
        default="",
        description="Model id for summarising. Empty means use the run's own model.",
    )
    enabled: bool = Field(
        default=True,
        description="Master switch. False removes the middleware entirely.",
    )

    @property
    def trigger_tokens(self) -> int:
        """Absolute token count at which compaction runs."""
        return int(self.max_context_tokens * self.soft_trigger_ratio)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "ContextPolicy":
        """Build the policy from CTX_* variables, falling back to defaults.

        Never raises. A malformed value logs a warning and yields the default,
        because a typo in one threshold must not stop every agent from starting.
        """
        if environment is None:
            from app.server.runtime_settings import effective_environment

            try:
                environment = effective_environment()
            except Exception:  # noqa: BLE001 - the environment is still valid config
                import os

                environment = dict(os.environ)

        def _read(name: str, default, cast):
            raw = str(environment.get(name, "")).strip()
            if not raw:
                return default
            try:
                return cast(raw)
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed %s=%r; using %r", name, raw, default)
                return default

        def _flag(raw: str) -> bool:
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            max_context_tokens=_read("CTX_MAX_TOKENS", 75_000, int),
            soft_trigger_ratio=_read("CTX_SOFT_TRIGGER_RATIO", 0.8, float),
            keep_recent_messages=_read("CTX_KEEP_MESSAGES", 20, int),
            trim_tokens_to_summarize=_read("CTX_SUMMARY_BUDGET", 4_000, int),
            compaction_model=str(environment.get("CTX_COMPACTION_MODEL", "")).strip(),
            enabled=_read("CTX_COMPACTION_ENABLED", True, _flag),
        )


__all__ = ["ContextPolicy"]
```

#### Step 1.2 — Verify

```bash
PYTHONPATH=src ENV=development python -c "
from app.agents.context_policy import ContextPolicy
p = ContextPolicy.from_environment({})
print('defaults    :', p.max_context_tokens, p.soft_trigger_ratio, p.trigger_tokens)
q = ContextPolicy.from_environment({'CTX_MAX_TOKENS':'32000','CTX_SOFT_TRIGGER_RATIO':'0.7'})
print('configured  :', q.max_context_tokens, q.trigger_tokens)
r = ContextPolicy.from_environment({'CTX_MAX_TOKENS':'not-a-number'})
print('malformed   :', r.max_context_tokens)
s = ContextPolicy.from_environment({'CTX_COMPACTION_ENABLED':'false'})
print('disabled    :', s.enabled)
"
```

Expected:
```
defaults    : 75000 0.8 60000
configured  : 32000 22400
malformed   : 75000
disabled    : False
```

---

### Phase 2 — Context store (the middleware's backend)

#### Step 2.1 — Create `src/app/agents/context_store.py`

```python
"""Where compaction keeps what it takes out of the conversation.

`SummarizationMiddleware` requires a backend of its own, separate from the
agent's. It is used to hold content lifted out of the message history.

This is deliberately **not** the run workspace. The workspace is product
output: it is listed as run artifacts, archived to object storage when a run
finishes, and shown in the artifact viewer. Context bookkeeping in there would
appear to the user as something the product produced.

`DATA_DIR/context/<thread id>/` is per-run, survives a restart, is inspectable
when a run misbehaves, and is invisible to everything that treats the workspace
as deliverable.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


def context_root() -> Path:
    """The directory under which every run's context data lives."""
    configured = os.environ.get("CTX_STORE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "context").expanduser().resolve()


def _safe_segment(value: str) -> str:
    """Reduce an identifier to one safe path segment."""
    cleaned = _UNSAFE.sub("-", Path(str(value)).name).strip("-")
    return cleaned[:120] or "thread"


def context_directory(thread_id: str) -> Path:
    """Create and return the context directory for one agent thread."""
    root = context_root()
    directory = (root / _safe_segment(thread_id)).resolve()
    if directory != root and root not in directory.parents:
        raise ValueError(f"Refusing to use a context directory outside {root}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_context_backend(thread_id: str):
    """A filesystem backend scoped to one agent thread.

    `FilesystemBackend` ships with deepagents; a hand-written backend would have
    to implement read/write/edit/ls/glob/grep/delete/upload_files/download_files
    plus their async twins, and getting any of them wrong fails at compaction
    time rather than at construction time.
    """
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=str(context_directory(thread_id)))


def discard_context(thread_id: str) -> None:
    """Remove one thread's context data. Never raises."""
    try:
        directory = context_directory(thread_id)
    except ValueError:
        return
    shutil.rmtree(directory, ignore_errors=True)


__all__ = [
    "build_context_backend",
    "context_directory",
    "context_root",
    "discard_context",
]
```

#### Step 2.2 — Verify

```bash
PYTHONPATH=src ENV=development DATA_DIR=/tmp/ctxcheck python -c "
from app.agents.context_store import build_context_backend, context_directory, discard_context
d = context_directory('thread-abc:principal_architect:1234')
print('directory  :', d)
print('created    :', d.is_dir())
b = build_context_backend('thread-abc')
print('backend    :', type(b).__name__)
print('has read   :', callable(getattr(b, 'read', None)))
print('has write  :', callable(getattr(b, 'write', None)))
discard_context('thread-abc')
print('discarded  :', not (d.parent / 'thread-abc').exists())
"
```

Expect a directory under `/tmp/ctxcheck/context/`, backend type `FilesystemBackend`, both methods present.

Also confirm containment:

```bash
PYTHONPATH=src ENV=development DATA_DIR=/tmp/ctxcheck python -c "
from app.agents.context_store import context_directory
print(context_directory('../../etc/passwd'))
"
```

The path must stay under `/tmp/ctxcheck/context/`. It will be a sanitised segment, not a traversal.

---

### Phase 3 — Wire compaction into every role agent

#### Step 3.1 — Edit `src/app/agents/role_agent.py`

**3.1a — Add imports.** Find:

```python
from deepagents.middleware.filesystem import FilesystemPermission
```

Add immediately after it:

```python
from deepagents.middleware.summarization import SummarizationMiddleware

from app.agents.context_policy import ContextPolicy
from app.agents.context_store import build_context_backend
```

**3.1b — Build the middleware.** Find this exact block:

```python
    # Inject directory instructions dynamically so every agent knows the artifact layout rules.
    full_system_prompt = (
        f"{system_prompt}\n\n"
        "CRITICAL DIRECTORY RULES:\n"
        "- Write all document artifacts (intakes, specs, plans, reports) inside the `docs/` folder (e.g., `docs/spec.md`).\n"
        "- Write all code artifacts inside the `<product_name>/` folder (based on the determined product name).\n"
    )
```

Insert immediately after it:

```python
    # Compaction. Built here rather than at module scope so a policy change
    # takes effect on the next agent, not the next restart.
    middleware = _compaction_middleware(name, checkpointer)
```

**3.1c — Pass it.** Find this exact block:

```python
    return create_deep_agent(
        model=selected_model,
        tools=tools,
        system_prompt=full_system_prompt,
        response_format=response_format,
```

Replace with:

```python
    return create_deep_agent(
        model=selected_model,
        tools=tools,
        system_prompt=full_system_prompt,
        response_format=response_format,
        middleware=middleware,
```

> **Do not add a `backend=` argument.** The agent keeps its in-memory `StateBackend`. Giving it a real filesystem backend would re-enable the built-in file tools against the workspace and hand agents a write path that skips the approval gate. The permissions block immediately below denies `/**` for exactly this reason. The middleware gets its own backend instead.

**3.1d — Add the helper.** Insert this function immediately **before** `def create_role_agent(`:

```python
def _compaction_middleware(agent_name: str, checkpointer: Any) -> list:
    """Summarise this agent's history before it outgrows the model's window.

    Returns an empty list when compaction is disabled or cannot be built, so a
    failure here degrades to "no compaction" rather than "no agent".

    The thread id is not known at construction time - `_run_gated_agent` mints
    one per attempt - so the context directory is keyed by agent name. That is
    stable per role and adequate: the content is scratch space for the
    summariser, not run state.
    """
    policy = ContextPolicy.from_environment()
    if not policy.enabled:
        return []

    try:
        from app.models import build_default_chat_model

        if policy.compaction_model:
            from app.config import load_settings
            from app.server.runtime_settings import effective_environment

            environment = dict(effective_environment())
            environment["OPENAI_MODEL"] = policy.compaction_model
            summariser = build_default_chat_model(load_settings(environment))
        else:
            # The run's own model. Never a hardcoded hosted model id: this
            # deployment may serve a local endpoint, where an OpenAI model name
            # with no base URL or key fails on every compaction.
            summariser = build_default_chat_model()

        return [
            SummarizationMiddleware(
                summariser,
                backend=build_context_backend(agent_name),
                trigger=("tokens", policy.trigger_tokens),
                keep=("messages", policy.keep_recent_messages),
                trim_tokens_to_summarize=policy.trim_tokens_to_summarize,
            )
        ]
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning(
            "Could not build compaction middleware for %s; continuing without it",
            agent_name, exc_info=True,
        )
        return []
```

If `role_agent.py` has no `logger`, add near the top after the imports:

```python
import logging

logger = logging.getLogger(__name__)
```

#### Step 3.2 — Verify

```bash
PYTHONPATH=src ENV=development DATA_DIR=/tmp/ctxcheck python -c "
from app.agents.role_agent import _compaction_middleware
mw = _compaction_middleware('product_manager', None)
print('middleware count:', len(mw))
print('type            :', type(mw[0]).__name__ if mw else 'none')
"
```

Expect count `1` and type `SummarizationMiddleware`. If it prints `0`, the exception branch was taken — re-run with logging visible to see why:

```bash
PYTHONPATH=src ENV=development DATA_DIR=/tmp/ctxcheck python -c "
import logging; logging.basicConfig(level=logging.WARNING)
from app.agents.role_agent import _compaction_middleware
_compaction_middleware('product_manager', None)
"
```

Then confirm the disable switch:

```bash
PYTHONPATH=src ENV=development DATA_DIR=/tmp/ctxcheck CTX_COMPACTION_ENABLED=false python -c "
from app.agents.role_agent import _compaction_middleware
print('disabled ->', _compaction_middleware('product_manager', None))
"
```

Expect `[]`.

---

### Phase 4 — Survive an overflow that compaction did not prevent

#### Step 4.1 — Edit `src/app/graph/workflow.py`

**4.1a — Add a detector.** Insert immediately **before** `def _run_gated_agent(`:

```python
_CONTEXT_OVERFLOW_MARKERS = (
    "maximum context length",
    "context_length_exceeded",
    "context length exceeded",
    "too many tokens",
    "reduce the length of the messages",
    "prompt is too long",
)


def _is_context_overflow(error: BaseException) -> bool:
    """Whether this exception is the model refusing an oversized prompt.

    Matched on the message because providers disagree on the type: the same
    condition arrives as BadRequestError, OpenAIInvalidRequestError, or a plain
    ValueError depending on which client is in front of it.
    """
    return any(marker in str(error).lower() for marker in _CONTEXT_OVERFLOW_MARKERS)
```

**4.1b — Guard the resume path.** Find this exact line (it is inside `_run_gated_agent`):

```python
        result = resume_with_decision(agent, inner_thread_id, pending_decision)
```

Replace with:

```python
        try:
            result = resume_with_decision(agent, inner_thread_id, pending_decision)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is overflow
            if not _is_context_overflow(exc):
                raise
            return _context_overflow_update(stage_name, exc)
```

**4.1c — Guard the fresh-invoke path.** Find this exact line:

```python
        result = agent.invoke(initial_request, config={"configurable": {"thread_id": inner_thread_id}})
```

Replace with:

```python
        try:
            result = agent.invoke(initial_request, config={"configurable": {"thread_id": inner_thread_id}})
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is overflow
            if not _is_context_overflow(exc):
                raise
            return _context_overflow_update(stage_name, exc)
```

**4.1d — Add the update builder.** Insert immediately after `_is_context_overflow`:

```python
def _context_overflow_update(stage_name: str, error: BaseException) -> dict[str, Any]:
    """State update for a stage the model refused as too large.

    `stage` must name a real node. `_route_from_stage` returns it verbatim and
    the conditional-edge map is built from `_NODE_NAMES`, so any other value is
    a KeyError that kills the run instead of failing it - which is worse than
    the overflow it was meant to handle.
    """
    logger.error("Context overflow in stage %s: %s", stage_name, error)
    return {
        "stage": "failed",
        "error": (
            f"The '{stage_name}' stage exceeded the model's context window even after "
            "compaction. Reduce CTX_MAX_TOKENS to compact sooner, use a model with a "
            "larger window, or split the work into smaller stages."
        ),
        "pending_approval": None,
        "pending_inner_thread_id": None,
        "pending_decision": None,
    }
```

#### Step 4.2 — Verify

```bash
PYTHONPATH=src ENV=development python -c "
from app.graph.workflow import _is_context_overflow, _context_overflow_update, _NODE_NAMES
print('detects openai  :', _is_context_overflow(ValueError(\"This model's maximum context length is 8192 tokens\")))
print('detects code    :', _is_context_overflow(Exception('context_length_exceeded')))
print('ignores others  :', _is_context_overflow(ValueError('connection refused')))
u = _context_overflow_update('principal_architect', Exception('boom'))
print('stage is a node :', u['stage'] in _NODE_NAMES)
print('stage           :', u['stage'])
"
```

Expected: `True`, `True`, `False`, `True`, `failed`.

---

### Phase 5 — Bound the first architect request

This is the largest measured cost (Part 1.1) and summarisation cannot touch it.

#### Step 5.1 — Edit `src/app/agents/principal_architect.py`

Find:

```python
REVISION_DOCUMENT_BUDGET = 20_000
```

Add immediately after that constant and its docstring:

```python
INITIAL_DOCUMENT_BUDGET = int(os.environ.get("CTX_ARCHITECT_DOCUMENT_BUDGET", "40000"))
"""Characters of the original upload to carry into the *first* request.

Measured on a real run: seven documents totalling 135,821 characters made the
architect's first request ~35,200 tokens, of which 96% was those documents -
sitting beside `product_intake`, which is the product manager's distillation of
the same material. The structured response came back with required sections
empty, the signature of a model with almost no room left to answer in.

Higher than the revision budget because the first pass is the one that has to
read the brief. Set to 0 to send everything.
"""
```

Ensure `import os` is present at the top of the file; add it if not.

Then find, inside `build_architecture_request`:

```python
        f"--- Original Uploaded Documents ---\n{document.text}\n\n"
```

Replace with:

```python
        f"--- Original uploaded documents ---\n"
        f"{_document_excerpt(document, INITIAL_DOCUMENT_BUDGET) if INITIAL_DOCUMENT_BUDGET else document.text}\n\n"
```

`_document_excerpt` already exists in this file and already appends a visible note saying how much was trimmed.

#### Step 5.2 — Verify

```bash
PYTHONPATH=src ENV=development python -c "
from app.documents import DocumentContent
from app.agents.principal_architect import build_architecture_request, INITIAL_DOCUMENT_BUDGET
from app.state import RepositoryContext
d = DocumentContent(source_path='x', source_type='markdown', text='D'*135821, truncated=False)
r = RepositoryContext(root_path='/w', branch='main', commit='abc', status='clean')
req = build_architecture_request('intake', 'tools', 'stack', r, d)
n = len(req['messages'][0]['content'])
print('budget      :', INITIAL_DOCUMENT_BUDGET)
print('request size:', n, 'chars ~', n//4, 'tokens')
print('trim noted  :', 'trimmed to' in req['messages'][0]['content'])
"
```

Expect roughly 45,000 characters (~11k tokens) instead of ~141,000 (~35k tokens), and `trim noted: True`.

If `RepositoryContext(...)` raises for missing fields, read its definition in `src/app/state.py` and pass whatever it requires — the assertion being checked is the size, not the constructor.

---

### Phase 6 — Journal oversized tool output

`SandboxExecutor` already truncates at `MAX_OUTPUT_SIZE`; the remainder is discarded. Keep the truncation where it is and write the full text to disk first, so a build log that mattered is still recoverable.

> Do **not** add a second truncation layer in `agent_toolkit.py` as the previous draft did. Two independent caps on the same string is how one of them silently stops mattering.

#### Step 6.1 — Create `src/app/tools/journal.py`

```python
"""Keeps the part of a tool's output that did not fit in the context.

`SandboxExecutor` truncates output at `MAX_OUTPUT_SIZE`; without this the
discarded remainder is gone, which matters most exactly when it matters at all -
a failing build whose real error was past the cap.

Written under DATA_DIR, not the workspace, for the same reason as the context
store: the workspace is product output and is archived and shown as such.
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


def journal_root() -> Path:
    configured = os.environ.get("CTX_JOURNAL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "journal").expanduser().resolve()


def write_entry(label: str, content: str) -> str | None:
    """Store `content` and return a short reference, or None if it could not be.

    Never raises. Losing a log copy must not fail the command that produced it.
    """
    if not content:
        return None
    try:
        safe = _UNSAFE.sub("-", label).strip("-")[:60] or "output"
        directory = journal_root()
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time())}-{safe}-{uuid.uuid4().hex[:8]}.log"
        (directory / name).write_text(content, encoding="utf-8")
        return name
    except OSError:
        logger.warning("Could not write journal entry for %s", label, exc_info=True)
        return None


def read_entry(name: str) -> str | None:
    """Read one entry back by the name `write_entry` returned."""
    safe = _UNSAFE.sub("-", name).strip("-")
    path = journal_root() / safe
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None


__all__ = ["journal_root", "read_entry", "write_entry"]
```

#### Step 6.2 — Edit `src/app/tools/sandbox.py`

Find this exact function:

```python
def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_SIZE:
        return text
    return text[:MAX_OUTPUT_SIZE] + f"\n...[truncated, exceeded {MAX_OUTPUT_SIZE} bytes]"
```

Replace with:

```python
def _truncate(text: str, label: str = "output") -> str:
    """Cap output for the model, keeping the whole of it on disk.

    The tail is kept as well as the head: a build's actual error is almost
    always in the last lines, and a head-only cut reliably discards it.
    """
    if len(text) <= MAX_OUTPUT_SIZE:
        return text

    from app.tools.journal import write_entry

    reference = write_entry(label, text)
    head = text[: int(MAX_OUTPUT_SIZE * 0.4)]
    tail = text[-int(MAX_OUTPUT_SIZE * 0.4):]
    pointer = (
        f"\n\n...[{len(text) - len(head) - len(tail)} bytes omitted"
        + (f"; full output saved as {reference}" if reference else "")
        + "]...\n\n"
    )
    return head + pointer + tail
```

Then update the two call sites so entries are labelled. In `_execute_here`, find:

```python
        return {
            "stdout": _truncate(result.stdout),
            "stderr": _truncate(result.stderr),
            "returncode": str(result.returncode),
        }
```

Replace with:

```python
        return {
            "stdout": _truncate(result.stdout, f"{role_name}-{argv[0]}-stdout"),
            "stderr": _truncate(result.stderr, f"{role_name}-{argv[0]}-stderr"),
            "returncode": str(result.returncode),
        }
```

There is a second, identical `return {` block at the end of the container-mode `execute` method. Apply the same change there; if `role_name` and `argv` are in scope (they are), use the same labels.

#### Step 6.3 — Verify

```bash
PYTHONPATH=src ENV=development DATA_DIR=/tmp/ctxcheck python -c "
from app.tools.sandbox import _truncate, MAX_OUTPUT_SIZE
from app.tools.journal import read_entry
import re
text = 'HEAD-MARKER' + 'x' * (MAX_OUTPUT_SIZE * 3) + 'TAIL-MARKER'
out = _truncate(text, 'demo')
print('shrunk      :', len(out) < len(text))
print('head kept   :', 'HEAD-MARKER' in out)
print('tail kept   :', 'TAIL-MARKER' in out)
m = re.search(r'saved as (\\S+)', out)
print('journalled  :', bool(m))
if m: print('recoverable :', read_entry(m.group(1)) == text)
print('short passes:', _truncate('tiny') == 'tiny')
"
```

All lines must be `True`.

---

### Phase 7 — Configuration and cleanup

#### Step 7.1 — Document the variables in `.env.example`

Append:

```bash
# ---------------------------------------------------------------------------
# Context compaction
# ---------------------------------------------------------------------------
# An agent's conversation is summarised once it passes
# CTX_MAX_TOKENS * CTX_SOFT_TRIGGER_RATIO, keeping the most recent
# CTX_KEEP_MESSAGES intact. Set CTX_MAX_TOKENS to the usable input window of
# the model you serve.
CTX_COMPACTION_ENABLED=true
CTX_MAX_TOKENS=75000
CTX_SOFT_TRIGGER_RATIO=0.8
CTX_KEEP_MESSAGES=20
CTX_SUMMARY_BUDGET=4000
# Empty means summarise with the run's own model. A value here is resolved
# through the same factory, so it inherits the base URL and credentials.
CTX_COMPACTION_MODEL=
# Characters of the uploaded documents sent to the architect's first request.
# 0 sends everything.
CTX_ARCHITECT_DOCUMENT_BUDGET=40000
# Where compaction scratch space and oversized tool output are kept. Both
# default under DATA_DIR and are deliberately outside the run workspace, which
# is treated as product output.
CTX_STORE_ROOT=
CTX_JOURNAL_ROOT=
```

#### Step 7.2 — Pass them to both containers in `docker-compose.yml`

In the `x-app-env: &app-env` block, add:

```yaml
  CTX_COMPACTION_ENABLED: ${CTX_COMPACTION_ENABLED:-true}
  CTX_MAX_TOKENS: ${CTX_MAX_TOKENS:-75000}
  CTX_SOFT_TRIGGER_RATIO: ${CTX_SOFT_TRIGGER_RATIO:-0.8}
  CTX_KEEP_MESSAGES: ${CTX_KEEP_MESSAGES:-20}
  CTX_SUMMARY_BUDGET: ${CTX_SUMMARY_BUDGET:-4000}
  CTX_COMPACTION_MODEL: ${CTX_COMPACTION_MODEL:-}
  CTX_ARCHITECT_DOCUMENT_BUDGET: ${CTX_ARCHITECT_DOCUMENT_BUDGET:-40000}
  CTX_STORE_ROOT: ${CTX_STORE_ROOT:-}
  CTX_JOURNAL_ROOT: ${CTX_JOURNAL_ROOT:-}
```

Do not use `${VAR:?}` anywhere. That form fires during interpolation for **every** compose command including `build`, which makes the image unbuildable without runtime values.

#### Step 7.3 — Delete context data with the run

In `src/app/server/runs.py`, find the run-deletion handler (it already removes uploads, workspace, checkpoints and event history). Add alongside the workspace removal:

```python
        try:
            from app.agents.context_store import discard_context

            discard_context(record.thread_id)
        except Exception:  # noqa: BLE001 - deletion of the run itself must not fail
            logger.warning("Could not remove context data for %s", run_id, exc_info=True)
```

Note: `_compaction_middleware` keys the directory by **agent name**, not thread id, so this cleans per-run data only once the middleware is changed to accept a thread id. Leave the call in place; it is correct once Phase 8 lands and harmless before.

#### Step 7.4 — Verify configuration reaches both containers

```bash
docker compose build app worker
docker compose up -d
docker compose exec -T worker python -c "
from app.agents.context_policy import ContextPolicy
p = ContextPolicy.from_environment()
print('enabled :', p.enabled)
print('window  :', p.max_context_tokens)
print('trigger :', p.trigger_tokens)
print('model   :', p.compaction_model or '(the run\\'s own)')
"
```

---

## Part 4 — Tests

Create `tests/test_context_compaction.py`. These are required, not optional: without them the middleware silently degrading to "no compaction" is indistinguishable from working.

```python
"""Keeping an agent's conversation inside the model's window."""

import pytest

from app.agents.context_policy import ContextPolicy


# --- policy --------------------------------------------------------------

def test_defaults_are_usable_with_no_configuration():
    policy = ContextPolicy.from_environment({})
    assert policy.enabled is True
    assert policy.trigger_tokens == 60_000


def test_the_window_and_ratio_are_configurable():
    policy = ContextPolicy.from_environment(
        {"CTX_MAX_TOKENS": "32000", "CTX_SOFT_TRIGGER_RATIO": "0.75"}
    )
    assert policy.trigger_tokens == 24_000


def test_a_malformed_value_falls_back_instead_of_raising():
    """A typo in one threshold must not stop every agent from starting."""
    policy = ContextPolicy.from_environment({"CTX_MAX_TOKENS": "seventy-five-thousand"})
    assert policy.max_context_tokens == 75_000


@pytest.mark.parametrize("raw,expected", [("false", False), ("0", False), ("true", True), ("on", True)])
def test_the_master_switch_reads_the_usual_spellings(raw, expected):
    assert ContextPolicy.from_environment({"CTX_COMPACTION_ENABLED": raw}).enabled is expected


def test_an_out_of_range_ratio_is_refused():
    with pytest.raises(Exception):
        ContextPolicy(soft_trigger_ratio=1.5)


# --- context store -------------------------------------------------------

def test_context_data_lives_outside_the_run_workspace(tmp_path, monkeypatch):
    """The workspace is product output: it is listed as artifacts and archived."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_STORE_ROOT", raising=False)
    from app.agents.context_store import context_directory

    directory = context_directory("thread-1")
    assert str(directory).startswith(str(tmp_path))
    assert "workspaces" not in str(directory)


def test_a_thread_id_cannot_escape_the_context_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_STORE_ROOT", raising=False)
    from app.agents.context_store import context_directory, context_root

    directory = context_directory("../../etc/passwd")
    assert str(directory).startswith(str(context_root()))


def test_the_backend_satisfies_what_the_middleware_calls(tmp_path, monkeypatch):
    """A hand-written backend that misses a method fails at compaction time,
    long after construction, so assert the surface up front."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.agents.context_store import build_context_backend

    backend = build_context_backend("thread-1")
    for method in ("read", "write", "ls", "glob", "grep", "delete"):
        assert callable(getattr(backend, method, None)), method


def test_discarding_removes_the_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.agents.context_store import context_directory, discard_context

    directory = context_directory("thread-gone")
    discard_context("thread-gone")
    assert not directory.exists()


# --- middleware construction --------------------------------------------

def test_compaction_is_attached_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_COMPACTION_ENABLED", raising=False)
    from app.agents.role_agent import _compaction_middleware

    middleware = _compaction_middleware("product_manager", None)
    assert len(middleware) == 1
    assert type(middleware[0]).__name__ == "SummarizationMiddleware"


def test_the_switch_removes_it_entirely(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CTX_COMPACTION_ENABLED", "false")
    from app.agents.role_agent import _compaction_middleware

    assert _compaction_middleware("product_manager", None) == []


def test_a_broken_summariser_degrades_to_no_compaction(tmp_path, monkeypatch):
    """No compaction is survivable. No agent is not."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.models.build_default_chat_model",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no provider")),
    )
    from app.agents.role_agent import _compaction_middleware

    assert _compaction_middleware("product_manager", None) == []


def test_the_agent_backend_is_not_replaced():
    """Giving the agent a real filesystem backend would re-enable the built-in
    file tools against the workspace, bypassing the approval-gated write tool."""
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent.create_role_agent)
    assert "backend=" not in source


# --- overflow handling ---------------------------------------------------

@pytest.mark.parametrize("message", [
    "This model's maximum context length is 8192 tokens",
    "context_length_exceeded",
    "prompt is too long",
])
def test_overflow_is_recognised(message):
    from app.graph.workflow import _is_context_overflow

    assert _is_context_overflow(ValueError(message))


def test_an_unrelated_error_is_not_treated_as_overflow():
    from app.graph.workflow import _is_context_overflow

    assert not _is_context_overflow(ValueError("connection refused"))


def test_the_overflow_update_names_a_real_node():
    """`_route_from_stage` returns the stage verbatim and the edge map is built
    from `_NODE_NAMES`, so an unknown name is a KeyError that kills the run."""
    from app.graph.workflow import _NODE_NAMES, _context_overflow_update

    update = _context_overflow_update("principal_architect", Exception("boom"))
    assert update["stage"] in _NODE_NAMES
    assert update["stage"] == "failed"


def test_the_overflow_update_clears_the_pause_fields():
    from app.graph.workflow import _context_overflow_update

    update = _context_overflow_update("principal_architect", Exception("boom"))
    assert update["pending_approval"] is None
    assert update["pending_decision"] is None


# --- journal -------------------------------------------------------------

def test_oversized_output_keeps_head_and_tail(tmp_path, monkeypatch):
    """A build's real error is almost always in the last lines."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.tools.sandbox import MAX_OUTPUT_SIZE, _truncate

    text = "HEAD" + "x" * (MAX_OUTPUT_SIZE * 3) + "TAIL"
    out = _truncate(text, "demo")
    assert "HEAD" in out and "TAIL" in out
    assert len(out) < len(text)


def test_the_full_output_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import re

    from app.tools.journal import read_entry
    from app.tools.sandbox import MAX_OUTPUT_SIZE, _truncate

    text = "y" * (MAX_OUTPUT_SIZE * 2)
    match = re.search(r"saved as (\S+)", _truncate(text, "demo"))
    assert match
    assert read_entry(match.group(1)) == text


def test_short_output_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.tools.sandbox import _truncate

    assert _truncate("all good") == "all good"


def test_a_journal_failure_does_not_break_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.tools.journal.write_entry", lambda *a, **k: None)
    from app.tools.sandbox import MAX_OUTPUT_SIZE, _truncate

    out = _truncate("z" * (MAX_OUTPUT_SIZE * 2), "demo")
    assert "omitted" in out


# --- request budget ------------------------------------------------------

def test_the_architect_first_request_is_bounded():
    """Measured: 7 documents = 135,821 chars made this request ~35,200 tokens,
    96% of it raw documents, sitting beside the intake that distils them."""
    from app.agents.principal_architect import INITIAL_DOCUMENT_BUDGET, build_architecture_request
    from app.documents import DocumentContent
    from app.state import RepositoryContext

    document = DocumentContent(
        source_path="x", source_type="markdown", text="D" * 135_821, truncated=False
    )
    repository = RepositoryContext(
        root_path="/w", branch="main", commit="abc", status="clean"
    )
    content = build_architecture_request("i", "t", "s", repository, document)["messages"][0]["content"]

    assert len(content) < 60_000
    assert "trimmed to" in content
    assert INITIAL_DOCUMENT_BUDGET > 0
```

Run:

```bash
PYTHONPATH=src ENV=development python -m pytest tests/test_context_compaction.py -q --no-cov
```

`RepositoryContext` requires exactly `root_path`, `branch`, `commit` and `status`; `dependency_files` and `entry_points` are optional. If it still fails, read `src/app/state.py` and supply what it asks for - but do not weaken the size assertion to make the test pass.

---

## Part 5 — Full verification

Run in order. Every one must pass before this work is considered done.

```bash
# 1. Whole suite, including the 80% coverage gate.
PYTHONPATH=src ENV=development python -m pytest tests/ -q --tb=short

# 2. No new security findings.
python -m bandit -r src/app -ll

# 3. Frontend still compiles (the image build runs tsc -b).
cd langchain-ui && npx tsc -b && cd ..

# 4. Images build and the stack comes up healthy.
docker compose build app worker
docker compose up -d
sleep 25
docker compose ps
curl -s http://localhost:8000/api/health/ready

# 5. Compaction is actually attached in the deployed worker.
docker compose exec -T worker python -c "
from app.agents.role_agent import _compaction_middleware
from app.agents.context_policy import ContextPolicy
p = ContextPolicy.from_environment()
mw = _compaction_middleware('principal_architect', None)
print('enabled  :', p.enabled)
print('trigger  :', p.trigger_tokens, 'tokens')
print('attached :', [type(m).__name__ for m in mw])
"
```

Step 5 must print a non-empty `attached` list. An empty one means the exception branch was taken and compaction is silently off — the exact failure these tests exist to catch.

### End-to-end confirmation

Start a run with a large document set and watch the worker:

```bash
docker compose logs -f worker | grep -iE "summar|compact|context|overflow"
```

A healthy long run shows summarisation firing and then continuing. Reaching a terminal stage without a context error is the actual success criterion.

---

## Part 6 — Deliberately deferred

State these rather than leaving them implied.

1. **Settings-API exposure of `CTX_*`.** Requires extending `SettingsUpdate`, `SettingsView`, `SETTABLE_KEYS` and the Settings page together. Environment configuration works now; the UI is a separate change.

2. **Per-thread context directories.** `_compaction_middleware` keys by agent name because `_run_gated_agent` mints the thread id later. Threading it through means changing the `create_*_agent` signature for all ten factories. The current scoping is adequate — the content is summariser scratch space, not run state — but per-thread is cleaner and makes Step 7.3's cleanup exact.

3. **Real token counting.** `count_tokens_approximately` is the middleware default and is an estimate. A model-specific tokenizer would be more accurate; the trigger ratio absorbs the error in the meantime.

4. **Compaction on the outer graph state.** This plan compacts *inner* agent conversations. The outer `WorkflowGraphState` accumulates structured outputs across sprints and has its own growth curve. Not a problem yet; measure before acting.

5. **Restructuring document intake.** The previous draft's Phase 5 proposed replacing concatenation with an `INDEX.md` the product manager reads on demand. That is a sound direction and a real change to `documents.py`, `uploads.py` and the product manager's prompt and tools — too large to bundle here, and Phase 5's request budget addresses the measured cost more cheaply.

---

## Appendix — Verified API reference

Read from the installed packages, not from memory. If any of this disagrees with the code you are editing, trust the code and re-verify.

**`create_deep_agent`** accepts, among others: `model`, `tools`, `system_prompt`, `middleware`, `subagents`, `permissions`, `backend`, `interrupt_on`, `response_format`, `state_schema`, `checkpointer`, `store`, `name`.

**`SummarizationMiddleware.__init__`**
```
(model: str | BaseChatModel, *, backend: BackendProtocol,
 trigger: ContextSize | TriggerClause | list[...] | None = None,
 keep: ContextSize = ('messages', 20),
 token_counter: TokenCounter = count_tokens_approximately,
 summary_prompt: str = <default>,
 trim_tokens_to_summarize: int | None = 4000,
 truncate_args_settings: TruncateArgsSettings | None = None)
```

**`ContextSize`**
```
tuple[Literal['fraction'], float] | tuple[Literal['tokens'], int] | tuple[Literal['messages'], int]
```

**`BackendProtocol` methods**
```
read write edit ls glob grep delete upload_files download_files
aread awrite aedit als aglob agrep adelete aupload_files adownload_files
```

**Backends available:** `StateBackend()`, `FilesystemBackend(root_dir=None, virtual_mode=True, max_file_size_mb=10)`, `StoreBackend`, `CompositeBackend(default, routes, *, artifacts_root='/')`, `ContextHubBackend`, `LocalShellBackend`, `LangSmithSandbox`.

**Anchor lines confirmed present**

| File | Anchor |
|---|---|
| `src/app/graph/workflow.py:352` | `result = resume_with_decision(agent, inner_thread_id, pending_decision)` |
| `src/app/graph/workflow.py:373` | `result = agent.invoke(initial_request, config={"configurable": {"thread_id": inner_thread_id}})` |
| `src/app/agents/role_agent.py` | `from deepagents.middleware.filesystem import FilesystemPermission` |
| `src/app/agents/role_agent.py` | `    return create_deep_agent(` |
| `src/app/tools/sandbox.py` | `def _truncate(text: str) -> str:` |
| `src/app/agents/principal_architect.py` | `REVISION_DOCUMENT_BUDGET = 20_000` |

**`RepositoryContext` constructor:** required `root_path`, `branch`, `commit`, `status`; optional `allow_subdirectories`, `dependency_files`, `entry_points`.

**`_truncate` call sites:** two, at `src/app/tools/sandbox.py:377` (in-container mode) and `:452` (container mode). `argv` and `role_name` are in scope at both, so the same labelled call works in each.

**Functions that do NOT exist** (referenced by the previous draft): `process_upload` in `uploads.py`; `agent_state` as a variable in `_run_gated_agent`; `save`/`load` on `BackendProtocol`.
