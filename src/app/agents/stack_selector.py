"""Stack Selector Agent (Phase 2).

This role worker consumes the approved product intake and the Tools and Models
output, and produces a single unified TechnologyStack choice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field

from app.agents.role_agent import create_role_agent
from app.agents.tools_models import TechnologyStack
from app.state import RepositoryContext

_STAGE = "stack_selector"
_NAME = "stack_selector"


class StackSelectorOutput(BaseModel):
    """Structured technology stack selection."""

    model_config = ConfigDict(extra="forbid")

    technology_stack: TechnologyStack = Field(..., description="The chosen integrated stack.")
    rationale: str = Field(..., description="Why this stack was chosen.")


def build_stack_selector_request(
    product_intake_text: str, tools_models_text: str, repository: RepositoryContext
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved product intake and tools models."""
    brief = (
        f"Repository root: {repository.root_path} "
        f"(branch: {repository.branch}, commit: {repository.commit})\n\n"
        f"--- Approved product intake ---\n{product_intake_text}\n\n"
        f"--- Tools and Models Comparison ---\n{tools_models_text}\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


_SYSTEM_PROMPT = """You are the Stack Selector for this workflow.

Your role is to turn an approved product intake and a technology comparison 
into a definitive, unified technology stack for the project.

Responsibilities:
- Choose the primary language, framework, database, and testing framework.
- The choices must be cohesive and compatible with each other.
- Output the selection as a structured TechnologyStack.

Constraints:
- Do not modify application source code and do not install dependencies.
- Ground choices in the provided product intake and tools models comparison.
- Keep the output structured and concise.
- Output ONLY the requested schema.
"""


def create_stack_selector_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """Create the Stack Selector role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=StackSelectorOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "StackSelectorOutput",
    "build_stack_selector_request",
    "create_stack_selector_agent",
]
