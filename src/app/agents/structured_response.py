"""One rule for every agent that owes the workflow a structured response.

A model that has finished its work sometimes writes the answer into the
conversation instead of returning it through the response schema. The text
looks right - often it is the exact JSON the schema asks for - but nothing
downstream receives it, because the workflow reads `structured_response` and
not the last message.

Measured twice in one afternoon, on two different agents:

- one run, product_manager: wrote `docs/product_intake.md`, then said
  "**Product intake complete.** Here is the structured summary:" and stopped.
  The next stage died on `KeyError: 'product_intake'`.
- one run, architecture_reviewer: printed `{"status": "approved",
  "findings": [...]}` as a message, wrote its document again, printed it
  again - five times - until the repeat guard stopped the stage.

Both agents already had some form of "return the structured response" in their
prompt. What neither had was the part that matters: saying that a response
written into the conversation is *not* returned. The models were not refusing
the instruction, they believed they had followed it.
"""

from __future__ import annotations

STRUCTURED_RESPONSE_RULE = """
How to finish:
- Your structured response is the whole of your output and the only thing the
  next stage receives. Return it through the response schema.
- A response written into the conversation is not returned. Printing the JSON
  as a message, or announcing "here is the structured summary" and then
  writing it out, leaves the next stage with nothing - it reads the schema,
  not your last message.
- Do not narrate that you are about to return it. Return it.
- Say it once. Re-sending the same answer, or re-writing a document you have
  already written, does not confirm it landed; the tool result already did.
""".strip()


__all__ = ["STRUCTURED_RESPONSE_RULE"]
