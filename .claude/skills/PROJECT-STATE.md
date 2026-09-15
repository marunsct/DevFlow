# Project State Index
Last updated: 2026-09-13T01:05Z

## Components
- `src/app/agents/product_manager.py` — server, product intake & spec distillation
- `src/app/agents/tools_models.py` — server, tools/models comparison
- `src/app/agents/principal_architect.py` — server, technical spec + ADRs
- `src/app/agents/architecture_reviewer.py` — server, architecture review gate
- `src/app/agents/scrum_master.py` — server, sprint planning
- `src/app/agents/milestone_reviewer.py` — server, milestone review gate
- `src/app/agents/security_reviewer.py` — server, security review gate
- `src/app/agents/stack_selector.py` — server, stack selection
- `src/app/agents/technical_lead.py` — server, technical lead planning
- `src/app/agents/specialists.py` — server, implementation specialists (db, backend, frontend, testing)
- `src/app/agents/role_agent.py` — server, agent creation factory
- `src/app/agents/approval.py` — server, approval gate logic
- `src/app/agents/context_policy.py` — server, context compaction config (200K window default)
- `src/app/agents/context_store.py` — server, context persistence
- `src/app/agents/text_budget.py` — server, text budget management
- `src/app/graph/workflow.py` — server, LangGraph workflow definition
- `src/app/graph/checkpointing.py` — server, checkpoint save/load
- `src/app/server/api.py` — server, REST API routes
- `src/app/server/runs.py` — server, run CRUD + approval endpoints
- `src/app/server/runner.py` — server, workflow runner orchestration
- `src/app/server/tasks.py` — server, Celery task definitions
- `src/app/server/auth.py` — server, JWT authentication
- `src/app/server/uploads.py` — server, file upload handling
- `src/app/server/object_store.py` — server, MinIO object storage
- `src/app/server/workspaces.py` — server, workspace management
- `src/app/server/runtime_settings.py` — server, runtime config API
- `src/app/server/events.py` — server, event streaming/logging
- `src/app/documents.py` — server, document content model
- `src/app/state.py` — server, repository context model
- `src/app/tools/sandbox.py` — server, command sandbox executor
- `src/app/tools/agent_toolkit.py` — server, agent tool definitions
- `src/app/tools/journal.py` — server, execution journal
- `src/app/tools/repository.py` — server, git repo tools
- `src/app/config.py` — server, app configuration
- `src/app/main.py` — server, FastAPI app entrypoint
- `src/app/models/router.py` — server, model routing
- `src/app/observability/metrics.py` — server, Prometheus metrics
- `src/app/observability/cost_tracker.py` — server, LLM cost tracking
- `src/app/evaluation/evaluators.py` — server, evaluation framework
- `src/app/scaffolding/executor.py` — server, code scaffolding executor
- `src/app/scaffolding/dependencies.py` — server, dependency resolution
- `src/app/scaffolding/registry.py` — server, scaffold registry
- `src/app/build/verifier.py` — server, build verification
- `src/app/deploy/compose_generator.py` — server, Docker Compose generation
- `src/app/deploy/docker_generator.py` — server, Dockerfile generation
- `src/app/deploy/ci_generator.py` — server, CI pipeline generation
- `src/app/testing/runner.py` — server, test runner integration
- `src/app/review.py` — server, review workflow logic
- `src/app/tracing.py` — server, OpenTelemetry tracing

## Routes
- `/api/auth/token` POST — JWT token issuance
- `/api/runs` POST — create new run (multipart file upload)
- `/api/runs/{run_id}` GET — get run status
- `/api/runs/{run_id}/start` POST — start a created run
- `/api/runs/{run_id}/approval` POST — record approval decision (`{"action": "approve"}`)
- `/api/runs/{run_id}/resume` POST — resume failed run from checkpoint

## Dependencies (key)
- langgraph — workflow orchestration
- fastapi — web framework
- celery — background task queue
- postgresql — persistent storage (checkpoints, runs)
- redis — message broker + cache
- minio — object storage for artifacts
- pydantic — data validation

## Conventions
- All agent files under `src/app/agents/`
- Server API under `src/app/server/`
- Graph/workflow in `src/app/graph/workflow.py`
- Docker services: `db`, `redis`, `minio`, `app`, `worker`
- Worker uses Celery with task time limit 3600s
- Context compaction enabled, trigger at 80% of CTX_MAX_TOKENS (200K default)
