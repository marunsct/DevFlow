# Technical Specification

## Product Scope
- **Coverage**: Core MVP features for asynchronous collaboration workspace:
  - Thread CRUD with role‑based permissions.
  - Video upload via pre‑signed MinIO URL.
  - Background queue (BullMQ) for transcription (Whisper) and summarization (OpenAI GPT‑4o).
  - Structured summary panel; action items extraction.
  - Review & approval workflow with status machine (DRAFT→PROCESSING→OPEN→RESOLVED).
  - Secure iframe preview integration using Tailscale/Funnel.
  - Basic export of ADR markdown.
- **Deferrals**:
  - Full‑text / semantic search service.
  - Advanced knowledge graph linking.
  - Jira/GitHub/Slack integrations (planned as add‑ons).
  - Enterprise SSO/SAML, audit logs beyond basic logs.
  - Localization and multi‑language support.

## Component Boundaries
1. **Next.js Frontend** – UI, SSR pages, API routes for CRUD.
2. **NestJS Backend** – REST services, authentication (Auth0/Keycloak), role checks.
3. **Prisma + PostgreSQL** – Data store for threads, users, approvals.
4. **MinIO Object Store** – Video blobs, transcripts, ADR files.
5. **BullMQ Worker Service** – Transcription & summarization jobs.
6. **NATS Streaming (JetStream)** – Pub/Sub for real‑time thread updates to clients.
7. **Tailscale/Funnel** – Secure tunnel provider for iframe previews.

## Domain Model (selected entities)
- `User` (id, email, roles).
- `Thread` (id, title, status, createdBy, orgId, videoUrl, transcriptPath, summary, actions).
- `Approval` (threadId, approverId, state, timestamp).

## API & Event Contracts
| Endpoint | Method | Description |
|---|---|---|
| `/api/threads` | POST | Create new thread – returns presigned MinIO URL.
| `/api/threads/:id` | GET | Retrieve thread details.
| `/api/threads/:id/approve` | POST | Submit approval action.

Events (NATS):
- `thread.created`
- `thread.status.changed`
- `thread.approved`

## Data Flows
1. User uploads video → presigned URL returned by backend.
2. Video stored in MinIO; worker picks up job via BullMQ.
3. Whisper transcribes to text file in MinIO.
4. GPT‑4o summarizes & extracts actions, writes JSON back to MinIO.
5. Backend updates Thread record and publishes `thread.status.changed`.
6. Frontend subscribes via WebSocket (NATS) for real‑time updates.

## Security & Privacy
- Role‑based access enforced at API layer (Admin/Contributor/Reviewer).
- All data stays on premises: PostgreSQL, MinIO, Redis, NATS, BullMQ workers.
- Video and transcript files are encrypted at rest in MinIO.
- Tailscale/Funnel creates isolated tunnel per workspace; iframe content is sandboxed.

## Reliability & Observability
- **Logging**: Elastic Stack (ELK) + OpenTelemetry instrumentation in NestJS.
- **Metrics**: Prometheus scrape from NestJS endpoints; Grafana dashboards.
- **Health Checks**: `/health` endpoint for all services.
- **Retries**: BullMQ retry policy with exponential back‑off for transcription jobs.

## Testing
- Unit/Integration tests with Jest + ts-jest for backend and frontend.
- E2E tests with Playwright covering thread creation, approval flow, iframe preview.
- Mock Prisma and external APIs in unit tests.

## Deployment
- Containerized Docker images for Next.js, NestJS API, BullMQ worker, Redis, MinIO, PostgreSQL, NATS.
- Deploy to Kubernetes (EKS/GKE/AKS) using Helm charts; environment variables per org for data isolation.
- CI/CD pipeline with GitHub Actions builds and pushes images.

## Open Questions
1. Minimum viable set of roles (Admin, Contributor, Reviewer).
2. Which tunnel provider(s) will be supported out‑of‑the‑box?
3. Granularity of approval policy (role‑based vs custom approver lists).
4. AI confidence threshold for auto‑acceptance.
5. Integration strategy with Jira/GitHub – paid add‑ons or core features.
6. Multi‑language transcription and summarization handling in MVP.

## Acceptance Criteria
- [ ] API endpoint `/api/threads` returns a valid presigned MinIO URL and creates thread record.
- [ ] Video upload to MinIO via the URL succeeds; worker job picks up file within 5 s.
- [ ] Whisper transcription completes and stores transcript JSON in MinIO.
- [ ] GPT‑4o summarization produces structured summary and action items; stored back to MinIO.
- [ ] Thread status transitions correctly through DRAFT→PROCESSING→OPEN→RESOLVED after approval.
- [ ] Frontend receives real‑time update via NATS/WebSocket after each status change.
- [ ] Secure iframe preview renders within sandboxed component when tunnel URL provided.
- [ ] ADR markdown can be generated and downloaded from thread view.
- [ ] Unit tests cover at least 80 % of backend services; E2E tests pass on CI.
- [ ] Deployment manifests deploy all components to Kubernetes without manual steps.

## Decisions
1. **Frameworks** – Use Next.js for frontend and NestJS for backend, as per approved plan.
2. **AI Transcription** – Whisper local in worker; fallback to OpenAI API if local fails.
3. **Summarization Model** – GPT‑4o via OpenAI API due to cost‑effectiveness and performance.
4. **Object Storage** – MinIO for all media and generated artifacts.
5. **Queue System** – BullMQ (Redis) chosen for job queue; NATS for pub/sub.
6. **Auth Provider** – Auth0 managed for simplicity, with fallback to Keycloak if data residency required.
7. **Observability** – Elastic Stack + OpenTelemetry for logs/tracing; Prometheus/Grafana for metrics.
8. **Testing Frameworks** – Jest + ts-jest for unit/integration; Playwright for E2E.
9. **Deployment** – Kubernetes with Helm charts, aligning with existing stack and scalability needs.
10. **Security** – All services run in isolated namespaces; data encrypted at rest; tunnel previews via Tailscale/Funnel.