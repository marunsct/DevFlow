"""`REASONING_KEPT_AFTER_AN_ANSWER` as the switch registry reads one: off in code and in compose until measured (M13)."""
from __future__ import annotations

from app.switches import is_on

#: `REASONING_KEPT_AFTER_AN_ANSWER` set to on or off overrides this.
ON_BY_DEFAULT = False


class _ReasoningKeptAfterAnAnswer:
    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A tool-calling reply keeps the reasoning carried with it after the stage gives an answer, so no "
                   "message already sent changes and the model server's prompt cache reuses the conversation; off, "
                   "an answer drops it from every earlier reply and the server reads the prompt again from there.")

    @staticmethod
    def enabled() -> bool:
        return is_on("REASONING_KEPT_AFTER_AN_ANSWER", ON_BY_DEFAULT)


reasoning_kept_switch = _ReasoningKeptAfterAnAnswer()
