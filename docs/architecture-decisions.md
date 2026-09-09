# Architecture Decision Records

Record one decision per section. Do not silently replace a decision; supersede it with a new entry.

## ADR-0001: Initial Product Architecture

- **Status:** Superseded by ADR-0002
- **Date:** 2026-09-03
- **Context:** The Hub needs durable, multi-tenant Decision Threads combining video, AI processing, approvals, and ADR-style knowledge capture.
- **Options considered:** A monolith with in-process media/AI work; a client-only application; a modular API with asynchronous workers.
- **Decision:** Consolidate on a Python backend (FastAPI + Celery) and a lightweight React SPA frontend. Use PostgreSQL for relational data, S3-compatible object storage for artifacts, and Redis for Celery task queues and rate limiting. Keep model providers replaceable so LM Studio/local inference can be used in development.
- **Rationale:** The split keeps uploads and user requests responsive, isolates long-running media and AI workloads, preserves relational integrity for approvals, and supports local or hosted model backends without changing product contracts.
- **Consequences:** More deployment and observability work; explicit job idempotency, retry, status, and data-retention behavior are required.
- **Validation evidence:** Principal Architect specification and Senior Architect Reviewer approval are required before implementation.

## ADR-0002: Pivot to React+Vite, FastAPI, and Celery

- **Status:** Accepted
- **Date:** 2026-09-09
- **Context:** Initial prototypes required rapid iteration in Python due to heavy reliance on LangChain and LangGraph for AI orchestration. The NestJS middle-tier added unnecessary overhead when Python could serve both the API and worker tiers effectively.
- **Options considered:** Continuing with Next.js/NestJS vs consolidating on a Python backend (FastAPI + Celery) and a lightweight React SPA.
- **Decision:** Consolidate the backend to Python using FastAPI for the API layer and Celery for asynchronous workers. Replace Next.js with a React+Vite Single Page Application (SPA) to simplify frontend deployment and tooling. Use PostgreSQL via psycopg2 (and psycopg2.pool) for persistence and SQLite/Postgres for LangGraph checkpointers.
- **Rationale:** This architecture drastically reduces context switching by keeping all backend logic (API and AI) in Python. Celery natively integrates with FastAPI and Python ecosystems. React+Vite provides a fast, lightweight frontend experience without the complexity of SSR unless needed.
- **Security and privacy impact:** Requires standard FastAPI security practices (CORS, dependency injection for auth). DB credentials and JWT secrets must be carefully managed in the environment.
- **Operational impact:** Simplifies the container topology (fewer language runtimes). 
- **Consequences and trade-offs:** We lose some Next.js built-in optimizations (like SSR) but gain significant velocity in AI feature development.
- **Supersedes:** ADR-0001

## Decision Log Template

### ADR-XXXX: <Decision Title>

- **Status:** Proposed | Accepted | Superseded | Rejected
- **Date:** YYYY-MM-DD
- **Context:**
- **Constraints:**
- **Options considered:**
- **Decision:**
- **Rationale:**
- **Security and privacy impact:**
- **Operational impact:**
- **Consequences and trade-offs:**
- **Validation evidence:**
- **Supersedes or related decisions:**
