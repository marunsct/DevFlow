import contextvars
from typing import Optional
from uuid import uuid4

_correlation_id_ctx_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

def get_correlation_id() -> Optional[str]:
    return _correlation_id_ctx_var.get()

def set_correlation_id(correlation_id: str) -> None:
    _correlation_id_ctx_var.set(correlation_id)
