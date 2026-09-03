# The Hub Technical Specification

**Status:** Draft for architecture review  
**Source:** `Detailed viability and product info.docx` and the repository scaffold  
**Date:** 2026-09-03

## 1. Product Summary

The Hub is a multi-tenant asynchronous collaboration workspace for engineering and consulting teams. Its primary artifact is a **Decision Thread**: a durable record that combines a short screen/webcam recording, transcript, AI-generated summary, structured action items, reviewer comments, approvals, and an eventual ADR export.

The product addresses meeting overload and the loss of architectural context in chat and one-off video messages. It differentiates through stateful decision workflows, formal sign-off, searchable decision history, and controlled previews of internal prototypes.

## 2. MVP Scope

### Included

- Organizations and isolated workspaces.
- Roles: Admin, Contributor, Reviewer, and Guest.
- Decision Thread lifecycle: `DRAFT -> PROCESSING -> OPEN -> RESOLVED -> ARCHIVED`.
- Screen and microphone recording in the browser.
- Direct upload to S3-compatible object storage using pre-signed URLs.
- Queue-backed transcription, summarization, and action extraction.
- Human editing and approval of AI-generated content.
- Approval policies and an audit trail for state changes and approvals.
- Thread metadata for risk level, affected systems, tags, and related tickets.
- Markdown ADR export when a thread is resolved.
- Secure, time-limited prototype preview links where required.

### Deferred

Semantic search and knowledge graph, Jira/GitHub/Linear/Slack integrations, analytics dashboards, SSO/SAML, SCIM, advanced retention/legal hold, automated redaction, and localization. Each requires a separate prioritization and architecture decision.

## 3. Proposed Architecture

- **Web:** Next.js with SSR/ISR, recording UI, transcript and summary review, approval workflow, and secure preview surface.
- **API:** NestJS modular service with Auth, Organizations, Workspaces, Threads, Approvals, Actions, Integrations, Audit, and Preview modules. OpenAPI is the API contract.
- **Database:** PostgreSQL with Prisma. Relational tables hold tenant and workflow integrity; JSONB is reserved for versioned AI metadata whose shape can evolve.
- **Storage:** MinIO or another S3-compatible service for original media and derived artifacts. Browser uploads use short-lived pre-signed URLs.
- **Jobs:** Redis and BullMQ with distinct idempotent jobs for media processing, transcription, post-processing/redaction, summarization, action extraction, and ADR generation.
- **AI worker:** FastAPI service exposing stable internal contracts for transcription, summarization, and action extraction. Model adapters support LM Studio/local models and hosted providers.
- **Observability:** Structured logs, metrics for job latency/failure/retry, audit events for user-visible changes, and LangSmith tracing for LangChain/LangGraph execution where enabled.

## 4. Core Domain Model

- `Organization`: tenant boundary and policy owner.
- `User`, `Membership`, `Role`: identity and authorization.
- `Workspace`: project/team boundary under an organization.
- `Thread`: title, problem statement, decision, risk, affected systems, status, owner, and timestamps.
- `MediaAsset`: storage key, content type, size, checksum, duration, and processing state.
- `Transcript`: versioned text and timestamped segments.
- `AiArtifact`: model/provider metadata, prompt version, output, confidence or review state, and source version.
- `ActionItem`: description, owner, due date, status, and external link.
- `ApprovalPolicy`, `Approval`: required roles/users, decision, comment, and timestamp.
- `Comment`: thread, transcript timestamp or preview target, author, body, and resolution state.
- `AuditEvent`: actor, action, target, before/after summary, request correlation ID, and timestamp.
- `Preview`: validated target, access policy, expiry, and revocation state.

Tenant identifiers must be present in every tenant-owned query. Authorization must be enforced server-side, not only in the UI.

## 5. Key Flows

### Create and Process a Thread

1. Contributor creates a draft with required context and risk level.
2. API authorizes workspace membership and returns an upload intent.
3. Browser uploads directly to object storage.
4. API records checksum and enqueues processing jobs.
5. Workers update status and persist versioned transcript and AI artifacts.
6. Contributor reviews and edits generated content.
7. Reviewers approve or reject according to policy.
8. When all required approvals exist, the thread may become `RESOLVED` and emit ADR generation.

Every transition must validate the current state, actor permissions, required data, and idempotency key. Failed jobs must be retryable without duplicating artifacts or actions.

### Prototype Preview

Only allow registered HTTPS targets or explicitly configured development tunnels. Use short-lived access, strict origin/domain validation, CSP, iframe sandbox restrictions, and no ambient credential forwarding. Treat preview content as untrusted.

## 6. Non-Functional Requirements

- Tenant isolation and authorization tests cover every API module.
- Uploads do not proxy large media through the API process.
- Long-running work is asynchronous and observable.
- Job retries are bounded, idempotent, and produce actionable errors.
- AI output is labeled as draft until a human accepts it.
- Secrets, tokens, raw credentials, and sensitive transcript data are excluded from logs.
- Data retention and deletion behavior is defined before production launch.
- API contracts and database migrations are backward-compatible within a release.
- Core user flows have automated tests and accessible keyboard-first UI behavior.

## 7. Open Questions Before Build

- Which identity provider and deployment target are required for the first customer?
- Is MinIO only for local development or also an accepted production deployment?
- Which media formats, maximum duration, and maximum upload size are supported?
- Which approval combinations are configurable in the MVP?
- Which local LM Studio model and context limits are the supported development baseline?
- What retention, deletion, export, and tenant data residency requirements apply?
- Which prototype tunnel provider is approved for production?

## 8. Decision References

The rationale for architectural choices is recorded in `docs/architecture-decisions.md`. New decisions must be added there before implementation relies on them.
