# Architecture Decision Records

Record one decision per section. Do not silently replace a decision; supersede it with a new entry.

## ADR-0001: Initial Product Architecture

- **Status:** Proposed
- **Date:** 2026-09-03
- **Context:** The Hub needs durable, multi-tenant Decision Threads combining video, AI processing, approvals, and ADR-style knowledge capture.
- **Options considered:** A monolith with in-process media/AI work; a client-only application; a modular API with asynchronous workers.
- **Decision:** Use a Next.js frontend, NestJS modular API, PostgreSQL with Prisma, S3-compatible object storage, Redis/BullMQ for jobs, and a separately deployable FastAPI AI worker. Keep model providers replaceable so LM Studio/local inference can be used in development.
- **Rationale:** The split keeps uploads and user requests responsive, isolates long-running media and AI workloads, preserves relational integrity for approvals, and supports local or hosted model backends without changing product contracts.
- **Consequences:** More deployment and observability work; explicit job idempotency, retry, status, and data-retention behavior are required.
- **Validation evidence:** Principal Architect specification and Senior Architect Reviewer approval are required before implementation.

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
