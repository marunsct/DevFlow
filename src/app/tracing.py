"""LangSmith tracing integration for the product-development workflow.

Step 7.3 of the workflow plan. Provides helpers to configure tracing and
attach safe metadata tags to each graph invoke, enabling per-role,
per-stage trace grouping in the LangSmith dashboard.

Tracing is conditional on LANGSMITH_TRACING=true in the environment.
When disabled, the helpers are no-ops that return empty dicts.
"""

import os
from typing import Any

def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled in the environment."""
    return os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")


def configure_tracing(settings: Any) -> None:
    """Configure LangSmith tracing environment variables from settings.

    Called once at startup. Validates that LANGSMITH_API_KEY and
    LANGSMITH_PROJECT are set when tracing is enabled.
    """
    if not is_tracing_enabled():
        return
        
    api_key = getattr(settings, "langsmith_api_key", os.getenv("LANGSMITH_API_KEY"))
    project = getattr(settings, "langsmith_project", os.getenv("LANGSMITH_PROJECT"))
    
    if not api_key:
        raise ValueError("LANGSMITH_API_KEY must be set when tracing is enabled.")
    if not project:
        raise ValueError("LANGSMITH_PROJECT must be set when tracing is enabled.")
        
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGCHAIN_PROJECT"] = project


def trace_metadata(
    run_id: str,
    stage: str,
    role: str,
    thread_id: str,
    *,
    product_name: str | None = None,
    decision_status: str | None = None,
) -> dict[str, Any]:
    """Return a metadata dict safe for LangSmith tracing.

    Strips sensitive content. Returns {} when tracing is disabled.
    """
    if not is_tracing_enabled():
        return {}
        
    metadata = {
        "run_id": run_id,
        "stage": stage,
        "role": role,
        "thread_id": thread_id,
    }
    try:
        from app.server.context import get_correlation_id
        corr_id = get_correlation_id()
        if corr_id:
            metadata["correlation_id"] = corr_id
    except ImportError:
        pass
    if product_name is not None:
        metadata["product_name"] = product_name
    if decision_status is not None:
        metadata["decision_status"] = decision_status
        
    return metadata


def make_run_name(product_name: str, thread_id: str) -> str:
    """Generate a human-readable LangSmith run name."""
    if not product_name:
        product_name = "Unknown Product"
    return f"{product_name} ({thread_id})"
