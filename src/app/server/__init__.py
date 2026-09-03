"""Web control plane for the product-development workflow.

Phase 6 of the workflow plan: a web application and API that lets users
upload product documents, start/resume/cancel runs, observe progress
via SSE or polling, and submit review and approval decisions.

This is an observer and controlled input surface - it cannot directly
mutate workflow state or bypass server-side gates.
"""
from __future__ import annotations

__all__ = ["create_app"]

def create_app(*args, **kwargs):
    """Lazy import to avoid loading FastAPI at module level."""
    from app.server.api import create_app as _create_app
    return _create_app(*args, **kwargs)
