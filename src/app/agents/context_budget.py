"""Every context budget, derived from one number: the model's context window.

Why this module exists
----------------------
The pipeline has roughly ten limits that all have to agree with how much the
model can actually hold: when the conversation is compacted, how many messages
survive compaction untouched, how much of an uploaded document reaches the first
message, how much of the specification a reviewer is given, how large a single
command's output may be, and how much the model may emit in one reply.

Until now each was an independent constant with its own default and its own
environment variable. Nothing related them, so every model change meant retuning
all ten by hand - and the history of this repository is largely the history of
getting that wrong:

- Budgets were cut five-fold to fix an overflow, then raised past their original
  values two commits later when the real window turned out to be larger.
- `CTX_MAX_TOKENS` was raised to 200,000 for a 262K model while the loaded model
  had a 115K window, so compaction would not have fired until well past the
  point of failure.
- A per-command output cap of 50 KB was multiplied by a protected tail of 20
  messages, guaranteeing ~123k tokens of context that compaction is defined not
  to touch - on a window that could not hold it.

None of those were careless. They are what happens when ten numbers have to be
kept mutually consistent by hand and only one of them is written down anywhere
near the reasoning.

The model here
--------------
One setting - the context window - is configured per model. Everything else is
derived from it by the arithmetic below, so a window that changes carries all
the budgets with it. Each derived value keeps its own environment variable as an
override, because a derivation good enough for every case does not exist; the
difference is that an override is now a deliberate exception rather than the
only mechanism.

The arithmetic reserves three things from the window before anything else may
use it: room for the model to reply, room for the system prompt and tool
schemas, and a margin. What remains is the input ceiling, and every other budget
is a fraction of that.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 100_000
"""Tokens assumed available when nothing is configured.

Deliberately modest. A window set too small wastes capacity; a window set too
large silently breaks every run, because compaction is scheduled to fire at a
point the model never reaches. Guessing low fails safely and visibly.
"""

CHARS_PER_TOKEN = 3
"""Characters per token, for converting between a text budget and a token budget.

Measured, not assumed. Every stored transcript records the characters sent and
the `input_tokens` the server counted for them, and across **10,841 request
pairs from 49 runs**:

    mean 2.98    median 2.99    p10 2.63    p90 3.37

It was 4, described as "a deliberately conservative one". It is not
conservative: 4 is the unsafe direction in **both** places this is used.

  tokens -> chars   `document_chars = tokens * CHARS_PER_TOKEN`
                    too high, and the text handed to the model is larger than
                    the token budget it was derived from.
  chars -> tokens   `tool_bytes // CHARS_PER_TOKEN`
                    too high, and the tokens a message will cost are
                    under-estimated.

At 4 against a real 2.99, every budget derived here allowed about a third more
text than it accounted for - on exactly the content this harness handles most,
which is code and JSON rather than English prose.

3 rather than the p10 of 2.63 deliberately. The remaining error at the dense
end is about 14%, which the fractions below already leave margin for; 2.63
would shrink every budget by a further 12% and buy compaction the evidence
does not call for. If overflow is ever seen again, this is the first number to
lower, and the distribution above is what to lower it against.

Still a constant, which is the part that is still wrong: this is a property of
the tokeniser and moves with the model. Deriving it per model at startup, from
the `usage_metadata` every call already returns, is §3.1's `ModelProfile` and
retires the whole class. Until then it is a measured constant rather than a
guessed one, which is the difference between this and what it replaced.
"""

FRAMING_TOKENS = 6_000
"""Reserved for the system prompt and tool schemas.

These are present in every request and belong to none of the budgets. Measured
against this pipeline's prompts, which run long: the shared role prompt alone is
several hundred lines before an agent's own brief is added.
"""

MIN_OUTPUT_TOKENS = 8_000
MAX_OUTPUT_TOKENS = 32_000
OUTPUT_FRACTION = 0.25
"""How much of the window is kept back for the model's reply.

The ceiling matters as much as the floor. Unbounded, one turn wrote 431,441
characters - about 108,000 tokens over 38 minutes - of prose where a structured
answer was wanted. The floor matters because the largest legitimate single reply
is an artifact write: a 51 KB specification is about 13,000 tokens, and a
ceiling below that truncates the document mid-sentence and corrupts the file.
"""

DOCUMENT_FRACTION = 0.25
"""Share of the input ceiling one interpolated document may occupy.

Applies to an uploaded brief in the architect's first message and to the
specification carried into a review. A quarter leaves the agent three quarters
of its room for the work that follows - the tool calls, their results, and the
answer - which is the part a document budget is competing with.
"""

TAIL_FRACTION = 0.5
"""Share of the input ceiling the protected tail may occupy.

`SummarizationMiddleware` keeps the most recent messages *untouched*, so
`keep_recent_messages` multiplied by the largest a message can be is a hard
floor on context that compaction cannot reduce. If that floor exceeds the
window, compaction cannot rescue the run no matter when it fires - which is
exactly how an iterative specialist died on a 50 KB output cap and a 20-message
tail.
"""

DEFAULT_KEEP_RECENT_MESSAGES = 15
SOFT_TRIGGER_RATIO = 0.8

TRUNCATE_ARGS_RATIO = 0.5
"""Where tool-call arguments in older messages are shortened.

Deliberately below `SOFT_TRIGGER_RATIO`, because this is the cheaper of the two
reliefs and should be tried first: shortening arguments is a local edit, while
summarisation costs a model call on the whole history.

It is also the better-aimed one here. The largest thing in this pipeline's
history is not conversation, it is artifact content: a `write_artifact` call
carries the whole document in its arguments, and a 51 KB specification then sits
in the context for the rest of the stage. The file is on disk the moment the
call returns, so nothing is lost by shortening the copy in the transcript.
"""

MAX_TOOL_ARG_CHARS = 2_000
"""How much of an older tool call's arguments to keep.

Enough to see what the call did - the path, the command, the opening of the
content - and not enough to carry a document. Recent calls are untouched; this
applies only behind the keep window, where the detail has already been acted on.
"""

MIN_VIABLE_WINDOW = 32_000

MIN_INPUT_CEILING_TOKENS = 16_000
"""What must remain for the conversation once the reply ceiling has taken its share.

A reply ceiling is only useful if there is a conversation left to reply to. This
is the floor an explicit `MODEL_MAX_OUTPUT_TOKENS` cannot eat into, so raising
the reply ceiling shrinks the conversation rather than eliminating it.
"""
"""The smallest window this pipeline can actually run in.

Not an arbitrary floor. Every request carries the framing (6,000) and must leave
room for a reply large enough to write an artifact (8,000), so 14,000 tokens are
spoken for before any work. What remains has to hold a brief, a specification
excerpt, and a conversation of tool calls and their results - and the protected
tail alone, which compaction may not touch, needs a few thousand of it.

Below roughly 32,000 the arithmetic still produces numbers, but they describe a
pipeline that cannot run: an input ceiling of two thousand tokens is smaller
than a single command's output. A window configured below this is raised to it,
because a budget that looks valid and cannot work is the worse failure - it
surfaces eight hours later as a dead stage rather than immediately as a
configuration error.
"""

MIN_ARTIFACT_REPLY_TOKENS = 4_000
"""Floor on the reply ceiling, even when explicitly overridden.

The largest legitimate single reply is an artifact write. Below this the model
is cut off mid-document and the file is written corrupted - a silent failure,
where the limit it was cut by is at least a visible one.
"""

MIN_TOOL_OUTPUT_BYTES = 4 * 1024
"""Floor on one command's captured output.

Below this a build log is cut before its error, which is the only part anybody
needed. The full output is always recoverable from the journal, so the cap
bounds what enters the conversation rather than what is kept.
"""


def _read_int(environment: Mapping[str, str], name: str) -> int | None:
    """An integer from the environment, or None when absent or malformed.

    Never raises: a typo in one budget must not stop every agent from starting.
    """
    raw = str(environment.get(name, "")).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("Malformed %s=%r; deriving it from the context window instead", name, raw)
        return None


def _the_deployment_s() -> Mapping[str, str]:
    """The deployment's environment with the settings page's values over it.

    The process environment alone describes the deployment as it was started:
    one worker read a 100,000-token window from it while the settings page
    said 130,000, and every budget followed the former.
    """
    try:
        from app.server.runtime_settings import effective_environment

        return effective_environment()
    except Exception:  # noqa: BLE001 - the deployed environment still stands
        return os.environ


def context_window(environment: Mapping[str, str] | None = None) -> int:
    """The configured context window, in tokens."""
    env = environment if environment is not None else _the_deployment_s()
    value = _read_int(env, "MODEL_CONTEXT_WINDOW")
    if value is None:
        return DEFAULT_CONTEXT_WINDOW
    # A window smaller than the framing plus a minimum reply cannot run anything.
    return max(value, MIN_VIABLE_WINDOW)


@dataclass(frozen=True)
class ContextBudget:
    """Every limit the pipeline needs, in agreement with one window.

    Build it with `ContextBudget.resolve()`; the derivation is in `from_window`
    so it can be reasoned about, and tested, without an environment.
    """

    window_tokens: int
    max_output_tokens: int
    input_ceiling_tokens: int
    keep_recent_messages: int
    document_budget_chars: int
    revision_budget_chars: int
    specification_budget_chars: int
    tool_output_bytes: int

    @property
    def trigger_tokens(self) -> int:
        """Where compaction fires - below the ceiling, so it fires in time."""
        return int(self.input_ceiling_tokens * SOFT_TRIGGER_RATIO)

    @property
    def truncate_args_trigger_tokens(self) -> int:
        """Where argument truncation fires - before summarisation, being cheaper."""
        return int(self.input_ceiling_tokens * TRUNCATE_ARGS_RATIO)

    @property
    def protected_tail_tokens(self) -> int:
        """The floor compaction cannot go below, given the tail it must keep."""
        return self.keep_recent_messages * (self.tool_output_bytes // CHARS_PER_TOKEN)

    @classmethod
    def from_window(
        cls,
        window_tokens: int,
        *,
        keep_recent_messages: int | None = None,
        max_output_tokens: int | None = None,
    ) -> "ContextBudget":
        # Clamped here as well as in `context_window`, so a budget built
        # directly - by a test, or by a caller passing a model's advertised
        # window - cannot produce limits that were never satisfiable.
        window_tokens = max(window_tokens, MIN_VIABLE_WINDOW)
        keep = keep_recent_messages or DEFAULT_KEEP_RECENT_MESSAGES

        if max_output_tokens is None:
            output = int(window_tokens * OUTPUT_FRACTION)
            output = max(MIN_OUTPUT_TOKENS, min(MAX_OUTPUT_TOKENS, output))
        else:
            # A chosen reply ceiling still has to leave a usable conversation
            # behind it. Reply, conversation and framing share one window, so
            # this is capped at what the window can actually spare rather than
            # accepted as given - `MODEL_MAX_OUTPUT_TOKENS=40000` on a 125k
            # window used to raise the reply ceiling while leaving the input
            # ceiling derived from the old one, so the two summed to 133,750
            # against a 125,000-token window.
            spare = window_tokens - FRAMING_TOKENS - MIN_INPUT_CEILING_TOKENS
            output = max(MIN_OUTPUT_TOKENS, min(int(max_output_tokens), spare))

        ceiling = window_tokens - output - FRAMING_TOKENS

        document_chars = int(ceiling * DOCUMENT_FRACTION) * CHARS_PER_TOKEN
        tool_bytes = max(
            MIN_TOOL_OUTPUT_BYTES,
            int(ceiling * TAIL_FRACTION / keep) * CHARS_PER_TOKEN,
        )

        # On a small window the output floor binds, and the tail it implies
        # would exceed its share of the ceiling - leaving compaction nothing it
        # is allowed to touch. Keep fewer messages rather than break the
        # invariant: a shorter protected tail still compacts, whereas a cap
        # below the floor cuts a build log before the error in it.
        tail_token_budget = int(ceiling * TAIL_FRACTION)
        per_message_tokens = max(1, tool_bytes // CHARS_PER_TOKEN)
        if per_message_tokens * keep > tail_token_budget:
            keep = max(2, tail_token_budget // per_message_tokens)

        return cls(
            window_tokens=window_tokens,
            max_output_tokens=output,
            input_ceiling_tokens=ceiling,
            keep_recent_messages=keep,
            document_budget_chars=document_chars,
            # A revision carries the document *and* the findings against it, so
            # it gets half: the review is the part that has to fit beside it.
            revision_budget_chars=document_chars // 2,
            specification_budget_chars=document_chars,
            tool_output_bytes=tool_bytes,
        )

    @classmethod
    def resolve(cls, environment: Mapping[str, str] | None = None) -> "ContextBudget":
        """The derived budget, with any explicit override applied on top.

        An override wins over the derivation, because no derivation fits every
        case. It is recorded here rather than read at each call site so that one
        place knows the full picture - and so `describe` can report a budget
        that is no longer internally consistent.
        """
        env = environment if environment is not None else _the_deployment_s()
        window = context_window(env)

        keep = _read_int(env, "CTX_KEEP_MESSAGES")
        # The reply ceiling is applied during derivation, not patched on after
        # it: everything else in the budget is measured from what the reply
        # leaves behind, so an override applied afterwards would describe a
        # window larger than the model has.
        derived = cls.from_window(
            window,
            keep_recent_messages=keep,
            max_output_tokens=_read_int(env, "MODEL_MAX_OUTPUT_TOKENS"),
        )

        overrides = {
            "input_ceiling_tokens": _read_int(env, "CTX_MAX_TOKENS"),
            "document_budget_chars": _read_int(env, "CTX_ARCHITECT_DOCUMENT_BUDGET"),
            "revision_budget_chars": _read_int(env, "CTX_REVISION_DOCUMENT_BUDGET"),
            "specification_budget_chars": _read_int(env, "CTX_SPECIFICATION_BUDGET"),
            "tool_output_bytes": _read_int(env, "SANDBOX_MAX_OUTPUT"),
        }
        applied = {name: value for name, value in overrides.items() if value is not None}
        if not applied:
            return derived

        from dataclasses import replace

        # An override is a deliberate exception, not a licence to break the
        # floors. A reply ceiling of 10 tokens truncates an artifact write
        # mid-document and corrupts the file; an output cap below 4 KB cuts a
        # build log before the error in it. Both are worse than the limit the
        # override was reaching for.
        if "max_output_tokens" in applied:
            applied["max_output_tokens"] = max(applied["max_output_tokens"], MIN_ARTIFACT_REPLY_TOKENS)
        if "tool_output_bytes" in applied:
            applied["tool_output_bytes"] = max(applied["tool_output_bytes"], MIN_TOOL_OUTPUT_BYTES)

        return replace(derived, **applied)

    def fits(self) -> bool:
        """Whether this budget can actually run inside its own window.

        False means compaction cannot rescue a long run: the protected tail
        alone, which compaction is defined not to touch, does not leave room for
        the reply and the framing.
        """
        return (
            self.protected_tail_tokens + self.max_output_tokens + FRAMING_TOKENS
            <= self.window_tokens
        )

    def describe(self) -> str:
        """One line per limit, for a startup log and for an operator."""
        lines = [
            f"context window            {self.window_tokens:>9,} tokens",
            f"  reply ceiling           {self.max_output_tokens:>9,} tokens",
            f"  input ceiling           {self.input_ceiling_tokens:>9,} tokens",
            f"  arguments trimmed at    {self.truncate_args_trigger_tokens:>9,} tokens",
            f"  compaction fires at     {self.trigger_tokens:>9,} tokens",
            f"  protected tail          {self.protected_tail_tokens:>9,} tokens "
            f"({self.keep_recent_messages} messages)",
            f"  document budget         {self.document_budget_chars:>9,} chars",
            f"  revision budget         {self.revision_budget_chars:>9,} chars",
            f"  specification budget    {self.specification_budget_chars:>9,} chars",
            f"  command output cap      {self.tool_output_bytes:>9,} bytes",
        ]
        if not self.fits():
            lines.append(
                "  WARNING: the protected tail, the reply and the framing do not "
                "fit in this window. Lower CTX_KEEP_MESSAGES or SANDBOX_MAX_OUTPUT, "
                "or raise the context window to match the model."
            )
        return "\n".join(lines)


def resolve(environment: Mapping[str, str] | None = None) -> ContextBudget:
    """Convenience wrapper so callers need not import the class."""
    return ContextBudget.resolve(environment)


__all__ = [
    "CHARS_PER_TOKEN",
    "MAX_TOOL_ARG_CHARS",
    "MIN_VIABLE_WINDOW",
    "DEFAULT_CONTEXT_WINDOW",
    "ContextBudget",
    "context_window",
    "resolve",
]
