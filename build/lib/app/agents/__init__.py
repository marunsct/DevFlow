"""Role-specific Deep Agents for the product-development workflow.

This package keeps each role worker in a focused module so the orchestration
graph can reason about the workflow as a set of narrow responsibilities rather
than one giant monolithic agent. Shared safety wiring (tools, the human
approval gate, checkpointing) lives in `role_agent.py` and `approval.py` so
every role module below only needs to supply what makes it different.
"""

from app.agents.architecture_reviewer import (
    ArchitectureReviewFinding,
    ArchitectureReviewOutput,
    create_architecture_reviewer_agent,
)
from app.agents.principal_architect import (
    ArchitectureDecisionRecord,
    TechnicalSpecificationOutput,
    create_principal_architect_agent,
)
from app.agents.product_manager import (
    ProductManagerOutput,
    approve_write_decision,
    build_intake_request,
    create_product_manager_agent,
    edit_write_decision,
    extract_pending_approval,
    reject_write_decision,
    resume_with_decision,
)
from app.agents.scrum_master import SprintDefinition, SprintPlanOutput, create_scrum_master_agent
from app.agents.specialists import SpecialistOutput, create_specialist_agent
from app.agents.technical_lead import (
    MilestonePlanOutput,
    SpecialistRole,
    SpecialistTask,
    create_technical_lead_agent,
)
from app.agents.tools_models import (
    TechnologyChoice,
    ToolsAndModelsOutput,
    create_tools_models_agent,
)

__all__ = [
    "ArchitectureDecisionRecord",
    "ArchitectureReviewFinding",
    "ArchitectureReviewOutput",
    "MilestonePlanOutput",
    "ProductManagerOutput",
    "SpecialistOutput",
    "SpecialistRole",
    "SpecialistTask",
    "SprintDefinition",
    "SprintPlanOutput",
    "TechnicalSpecificationOutput",
    "TechnologyChoice",
    "ToolsAndModelsOutput",
    "approve_write_decision",
    "build_intake_request",
    "create_architecture_reviewer_agent",
    "create_principal_architect_agent",
    "create_product_manager_agent",
    "create_scrum_master_agent",
    "create_specialist_agent",
    "create_technical_lead_agent",
    "create_tools_models_agent",
    "edit_write_decision",
    "extract_pending_approval",
    "reject_write_decision",
    "resume_with_decision",
]