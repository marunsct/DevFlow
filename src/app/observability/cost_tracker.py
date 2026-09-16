from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from typing import Dict, Any, List

class CostTrackingCallbackHandler(BaseCallbackHandler):
    """
    Tracks token usage and estimates costs for LangChain LLM calls.
    """
    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.successful_requests = 0
        self.estimated_cost = 0.0

    @staticmethod
    def _counts(response: LLMResult) -> tuple[int, int, int] | None:
        """Prompt, completion and total tokens, from wherever they arrived.

        A non-streamed response carries them in ``llm_output["token_usage"]``.
        A streamed one leaves ``llm_output`` as ``None`` and puts them on the
        aggregated message instead, so reading only the first place reports
        zero tokens for an entire run - which is what this handler did for
        every call once the models began streaming.
        """
        usage = (response.llm_output or {}).get("token_usage")
        if usage:
            p = usage.get("prompt_tokens", 0)
            c = usage.get("completion_tokens", 0)
            return p, c, usage.get("total_tokens", p + c)

        p = c = t = 0
        found = False
        for generations in response.generations:
            for generation in generations:
                metadata = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if not metadata:
                    continue
                found = True
                p += metadata.get("input_tokens", 0)
                c += metadata.get("output_tokens", 0)
                t += metadata.get("total_tokens", 0)
        return (p, c, t or p + c) if found else None

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        self.successful_requests += 1

        counts = self._counts(response)
        if counts:
            p_tokens, c_tokens, total = counts

            self.prompt_tokens += p_tokens
            self.completion_tokens += c_tokens
            self.total_tokens += total
            
            # Simple estimation (e.g. GPT-4o-mini rates approx)
            # This would ideally use a price map per model
            self.estimated_cost += (p_tokens * 0.15 / 1_000_000) + (c_tokens * 0.60 / 1_000_000)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "successful_requests": self.successful_requests,
            "estimated_cost_usd": round(self.estimated_cost, 6)
        }
