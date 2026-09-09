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

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        self.successful_requests += 1
        
        if response.llm_output and "token_usage" in response.llm_output:
            token_usage = response.llm_output["token_usage"]
            
            p_tokens = token_usage.get("prompt_tokens", 0)
            c_tokens = token_usage.get("completion_tokens", 0)
            
            self.prompt_tokens += p_tokens
            self.completion_tokens += c_tokens
            self.total_tokens += token_usage.get("total_tokens", p_tokens + c_tokens)
            
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
