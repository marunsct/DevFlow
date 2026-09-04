# The Hub: Sprint-Style Task Breakdown

This breakdown groups the engineering work into practical sprint-sized chunks.
Each sprint has a clear outcome, a list of tasks, and completion criteria.

> **New here?** Read [`the-hub-glossary.md`](./the-hub-glossary.md) first for
> plain-English definitions of every tool and term used below. The reasoning
> behind every decision — data model, API design, architecture — lives in
> [`the-hub-implementation-plan.md`](./the-hub-implementation-plan.md); this file
> is the time-boxed version of the same roadmap covered by
> [`the-hub-engineering-checklist.md`](./the-hub-engineering-checklist.md). All
> three describe the same plan — if anything here conflicts with the
> implementation plan, the implementation plan is correct.

---

## Sprint 1 — Foundation and local infra

### Objective
Set up the working local development environment and prove the core stack runs
together: three background services (database, cache/queue, file storage), each
running in its own Docker container.

### Tasks
- [ ] Verify Linux developer environment
  - [ ] Node.js 20 (`node -v`)
  - [ ] Python 3 (`python3 --version`)
  - [ ] Git (`git --version`, and `git config --global user.name`/`user.email`
        set)
  - [ ] build tools installed (`build-essential` on Ubuntu, needed by some npm
        packages that compile native code)
- [ ] Install Docker and Docker Compose (`docker --version`,
      `docker compose version`)
- [ ] Start local services in `infra/`
  - [ ] `cd infra && docker compose up -d`
  - [ ] Postgres
  - [ ] Redis
  - [ ] MinIO
- [ ] Verify container health
  - [ ] `docker compose ps` — all three services show healthy
  - [ ] `docker exec hub-postgres pg_isready -U postgres` → `accepting
        connections`
  - [ ] `docker exec hub-redis redis-cli ping` → `PONG`
  - [ ] MinIO console accessible at `http://localhost:9001`
        (`minioadmin`/`minioadmin`)
- [ ] Create shared environment config examples (checked into Git; the real
      `.env` files are not — see the glossary's "Secrets" entry for why)
  - [ ] backend `.env.example` (`DATABASE_URL`, `REDIS_URL`, `MINIO_ENDPOINT`,
        `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `JWT_SECRET`)
  - [ ] frontend `.env.example` (`NEXT_PUBLIC_API_URL`)
  - [ ] AI worker `.env.example` (`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`,
        `MINIO_SECRET_KEY`, LLM API key if using a cloud model)
- [ ] Document startup commands for the team (a short `README.md` at the repo
      root: "run `docker compose up -d` from `infra/`, then...")

### Deliverable
A working local environment where all infrastructure services run and
communicate correctly.

### Exit criteria
- `docker compose ps` shows all expected services healthy.
- Developers can start the stack with a documented command sequence.
- **Full command list and troubleshooting** if anything above fails:
  [implementation plan §8.3](./the-hub-implementation-plan.md#83-local-validation--the-exact-commands).

---

## Sprint 2 — Backend foundation and schema

### Objective
Bootstrap the backend, set up data models, and prepare the API for business
features.

### Tasks
- [ ] Initialize NestJS app in `backend/core-api` *(already scaffolded in this
      repo — confirm `npm run start:dev` works first)*
- [ ] Install backend dependencies *(already present — check with `npm ls`)*
- [ ] Configure environment variables (copy `.env.example` → `.env`, fill in
      real local values)
- [ ] Add the Prisma schema for the MVP domain — use the exact schema from
      [implementation plan §9.1](./the-hub-implementation-plan.md#91-domain-model-canonical-prisma-schema),
      saved to `backend/core-api/prisma/schema.prisma`
  - [ ] `User`
  - [ ] `Workspace`
  - [ ] `Thread`
  - [ ] `Comment`
  - [ ] `Approval`
  - [ ] `Attachment`
- [ ] Generate the Prisma client and run the migration
  - [ ] `npx prisma migrate dev --name init`
  - [ ] `npx prisma generate`
- [ ] Set up Swagger and the NestJS config module (`@nestjs/config`,
      `@nestjs/swagger`)
- [ ] Scaffold base modules
  - [ ] app
  - [ ] auth
  - [ ] threads
  - [ ] uploads
  - [ ] queue
- [ ] Run the app locally and confirm startup: `npm run start:dev`

### Deliverable
A backend that starts cleanly and has the persistent schema ready for business
logic.

### Exit criteria
- Prisma migration completes successfully (`npx prisma studio` shows the new,
  empty tables).
- `npm run start:dev` runs without startup errors.

---

## Sprint 3 — Thread creation and listing APIs

### Objective
Implement the first product workflow: create and retrieve decision threads.

### Tasks
- [ ] Define thread DTOs (small classes describing what a request body must
      contain — see glossary "DTO")
  - [ ] create
  - [ ] update
  - [ ] response
- [ ] Add thread validation rules (title required, creator required, workspace
      required — reject with `400` otherwise)
- [ ] Implement the service layer for thread creation
- [ ] Implement the thread list endpoint — `GET /api/v1/threads`
- [ ] Implement the thread detail endpoint — `GET /api/v1/threads/:id`
- [ ] Add a thread update endpoint (`PATCH /api/v1/threads/:id`); deletion is
      optional for MVP — archiving (status → `ARCHIVED`) is usually preferable to
      hard-deleting a decision record
- [ ] Add error handling and status responses (`400`, `401`/`403`, `404`)
- [ ] Write integration tests for key thread endpoints
- [ ] Validate API behavior with Postman, Insomnia, or a plain `curl` command —
      no frontend exists yet, and that's fine; the Swagger page from Sprint 2 is
      also useful here

### Deliverable
The API supports thread creation and retrieval as the core product entity.

### Exit criteria
- A valid thread can be created through the API.
- Thread list and detail endpoints return correct data.
- Validation fails clearly (with a useful `400` message) for bad inputs.

---

## Sprint 4 — Upload workflow and media storage

### Objective
Allow users to attach video or evidence files to a thread, using the
presigned-URL pattern explained in
[implementation plan §9.4](./the-hub-implementation-plan.md#94-upload-flow) —
the file goes straight from the browser to MinIO, never through the API server.

### Tasks
- [ ] Configure the MinIO client in NestJS (`@aws-sdk/client-s3`)
- [ ] Create the presigned upload endpoint —
      `POST /api/v1/threads/:id/upload-url`
- [ ] Add the upload confirmation endpoint —
      `POST /api/v1/threads/:id/confirm-upload`
- [ ] Store metadata in the database (the `Attachment` model)
  - [ ] file name
  - [ ] storage key
  - [ ] mime type
  - [ ] size
  - [ ] `threadId`
  - [ ] status (`UPLOADING` / `READY` / `FAILED`)
- [ ] Validate access permissions for thread upload (only someone with access to
      the thread can request an upload URL for it)
- [ ] Restrict file types and max size (e.g. `video/webm`/`video/mp4` only, cap
      at a size you choose such as 500 MB)
- [ ] Add upload failure and retry handling
- [ ] Verify the uploaded file can be retrieved from MinIO — check the MinIO
      console at `http://localhost:9001`

### Deliverable
A thread can include uploaded media and the backend tracks it properly.

### Exit criteria
- File upload completes successfully.
- Metadata persists correctly.
- Backend rejects invalid or unauthorized upload attempts.

---

## Sprint 5 — Async processing queue

### Objective
Move media processing into the background so the API remains responsive — the
`confirm-upload` call should return in milliseconds, not wait for AI processing
to finish. See glossary "Queue / job / worker" if this pattern is new to you.

### Tasks
- [ ] Configure BullMQ with Redis (`@nestjs/bullmq`)
- [ ] Create the `video-processing` queue
- [ ] Add producer logic when upload is confirmed (one line:
      `queue.add('process', { threadId, storageKey })` — see implementation plan
      §9.5 for the full consumer-side example too)
- [ ] Add a job consumer (`@Processor('video-processing')`)
- [ ] Add job status transitions, reflected on `Thread.status`
  - [ ] queued (`PROCESSING`)
  - [ ] processing
  - [ ] success (`IN_REVIEW`)
  - [ ] failed (stays visible with a clear failure state — never a silent stall)
- [ ] Add retry handling for transient failures (BullMQ job `attempts` option)
- [ ] Add a dead-letter or failed-job handling strategy (what happens after all
      retries are exhausted? at minimum, log it and leave the thread in a visible
      "failed" state a human can retry manually)
- [ ] Verify queue behavior through manual runs (trigger an upload, confirm the
      job runs and updates the thread)

### Deliverable
Media processing runs asynchronously instead of blocking the API request.

### Exit criteria
- Jobs are queued and processed reliably.
- Thread status changes reflect processing state.

---

## Sprint 6 — AI processing worker

### Objective
Turn uploaded media into useful transcript and summary data.

### Tasks
- [ ] Scaffold a FastAPI app in `ai-worker/`
- [ ] Create a Python virtual environment: `python3 -m venv .venv && source
      .venv/bin/activate`
- [ ] Install dependencies: `fastapi`, `uvicorn`, `httpx`, `pydantic`, `minio`,
      `openai-whisper`
- [ ] Implement the webhook or job-callback contract with the backend — matches
      [implementation plan §10.2](./the-hub-implementation-plan.md#102-input-and-output-contracts)
- [ ] Download the object from MinIO
- [ ] Extract audio from the video (e.g. via `ffmpeg`)
- [ ] Run Whisper transcription
- [ ] Run summary generation with an LLM, using the strict JSON-output prompt in
      [implementation plan §10.3](./the-hub-implementation-plan.md#103-the-summarization-prompt)
- [ ] Return structured output
  - [ ] transcript
  - [ ] summary
  - [ ] key points
  - [ ] action items
  - [ ] risk level
- [ ] Add graceful failures for missing audio, corrupt files, or an LLM response
      that isn't valid JSON — validate before saving, and mark the failure
      clearly rather than saving garbage
- [ ] Verify end-to-end AI processing on a sample upload — record a short test
      clip, upload it, and confirm a real transcript + summary come back

### Deliverable
The AI worker produces a usable transcript and decision summary for a thread.

### Exit criteria
- A sample video produces a transcript and summary.
- Failure states are explicit and visible to the user.

---

## Sprint 7 — Review comments and discussion flow

### Objective
Support review and discussion on the decision itself.

### Tasks
- [ ] Define the comment schema and data model (already in the canonical schema
      from Sprint 2)
- [ ] Implement the add-comment endpoint — `POST /api/v1/threads/:id/comments`
- [ ] Implement the get-comments endpoint (or include comments in the thread
      detail response — pick one and be consistent)
- [ ] Add comment validation rules (reject empty/whitespace-only content)
- [ ] Add timestamp support for context-linked comments
      (`timestampSeconds` — links a comment to a moment in the attached video)
- [ ] Add a thread detail response that includes comments
- [ ] Display comments in UI by creation time
- [ ] Add manual testing for comment creation and retrieval

### Deliverable
Users can discuss and annotate the decision in context.

### Exit criteria
- Comments are saved and visible on the thread detail view.
- Timestamps and ordering behave correctly.

---

## Sprint 8 — Approval workflow

### Objective
Create the formal decision resolution flow, using the canonical 7-status
lifecycle from
[implementation plan §5.1](./the-hub-implementation-plan.md#51-decision-states-canonical):
`DRAFT → PROCESSING → IN_REVIEW → APPROVED/REJECTED → REOPENED → ARCHIVED`.

### Tasks
- [ ] Define the approval model and schema (already in the canonical schema from
      Sprint 2)
- [ ] Implement the approve endpoint — `POST /api/v1/threads/:id/approve`
- [ ] Implement the reject endpoint — `POST /api/v1/threads/:id/reject`
- [ ] Add thread status transitions matching the state diagram in the
      implementation plan (MVP rule: **any one approval resolves the thread as
      `APPROVED`; any one rejection resolves it as `REJECTED`** — a multi-approver
      policy engine is a post-MVP feature, don't build it now)
- [ ] Prevent duplicate approval by the same approver — enforced at the database
      level via `@@unique([threadId, userId])` on the `Approval` model
- [ ] Add approval history records (the `Approval` rows are the history — never
      delete them, only add)
- [ ] Add UI actions for approve/reject
- [ ] Add tests for approved and rejected states

### Deliverable
A thread can move from review to a final approved or rejected state.

### Exit criteria
- One approver can approve or reject.
- Thread status updates correctly.
- Duplicate approval is prevented.

---

## Sprint 9 — Frontend MVP screens

### Objective
Build the first user-facing flow so the end-to-end product is testable.

### Tasks
- [ ] Initialize Next.js app: `npx create-next-app@latest frontend --typescript
      --tailwind`
- [ ] TypeScript and Tailwind setup *(the command above handles both)*
- [ ] Create layout and shell navigation
- [ ] Build thread list page
- [ ] Build new thread page
- [ ] Build thread detail page
- [ ] Add upload UI (wires up the `useMediaRecorder` hook and
      `uploadVideoToStorage` routine from implementation plan §11.3/§9.4)
- [ ] Add transcript and summary sections
- [ ] Add comment form
- [ ] Add approval controls
- [ ] Connect to backend APIs (`NEXT_PUBLIC_API_URL` from Sprint 1's
      `.env.example`)

### Deliverable
A basic working web app for creating and reviewing threads.

### Exit criteria
- Users can create a thread from the interface.
- Thread detail shows the uploaded file and AI output.
- Approval controls are visible and functional.

---

## Sprint 10 — End-to-end validation and product polish

### Objective
Verify the full flow works end-to-end and fix rough edges.

### Tasks
- [ ] Run the complete workflow manually
  - [ ] create thread
  - [ ] upload file
  - [ ] wait for AI processing to finish
  - [ ] comment
  - [ ] approve/reject
- [ ] Validate UI loading, empty, and error states
- [ ] Improve messaging for long-running operations (the AI processing step can
      take a minute or more — say so in the UI, don't just show a spinner with no
      context)
- [ ] Add user-friendly status banners
- [ ] Fix edge cases discovered during testing
- [ ] Ensure all required actions show up in logs and UI
- [ ] Confirm the app works from a completely clean environment (delete your
      local Docker volumes and `node_modules`, start over from Sprint 1's
      instructions, and see what breaks)

### Deliverable
The product is working from a user perspective, not just on the API level.

### Exit criteria
- End-to-end workflow passes reliably.
- Major edge cases are handled or documented.

---

## Sprint 11 — Security, privacy, and QA hardening

### Objective
Reduce risk before internal testing or release. Full detail in
[implementation plan §13](./the-hub-implementation-plan.md#13-security-and-hardening).

### Tasks
- [ ] Validate authorization on all thread and approval endpoints
- [ ] Restrict uploads by type and size
- [ ] Check access control for thread ownership
- [ ] Add CSP protections for the frontend
- [ ] Validate embed and URL safety (only relevant if the live-prototype-preview
      feature was built — see implementation plan §13)
- [ ] Review transcript privacy concerns (transcripts may contain sensitive
      spoken content — document the retention/access policy even if it's simple
      for MVP)
- [ ] Add secret management guidance (`.env` files kept out of Git — see glossary
      "Secrets")
- [ ] Run a final security smoke test
- [ ] Fix obvious weaknesses found in review

### Deliverable
The MVP is safe enough for internal usage and validation.

### Exit criteria
- No obvious unauthorized access path.
- Upload and decision flows are protected by basic app security.

---

## Sprint 12 — MVP release sign-off

### Objective
Prepare the project for a real validation cycle.

### Tasks
- [ ] Review the backlog and remove non-MVP items (anything from
      [implementation plan §17](./the-hub-implementation-plan.md#17-post-mvp-roadmap-from-the-product-research--not-to-build-yet)
      that crept into scope — cut it)
- [ ] Document setup steps for the team
- [ ] Create a known-issues list
- [ ] Run the release checklist
  - [ ] local stack starts (`docker compose up -d`)
  - [ ] thread flow works
  - [ ] AI processing works
  - [ ] approval flow works
  - [ ] frontend functions correctly
- [ ] Define the next-phase backlog (implementation plan §17 is a starting point)
- [ ] Final product sign-off

### Deliverable
A clean MVP candidate ready for internal validation.

### Exit criteria
- The team agrees the product is usable for limited real-world testing.
- Next-phase improvements are documented without scope drift.

---

## Recommended sprint sequence

1. Sprint 1 — Foundation and local infra
2. Sprint 2 — Backend foundation and schema
3. Sprint 3 — Thread creation and listing APIs
4. Sprint 4 — Upload workflow and media storage
5. Sprint 5 — Async processing queue
6. Sprint 6 — AI processing worker
7. Sprint 7 — Review comments and discussion flow
8. Sprint 8 — Approval workflow
9. Sprint 9 — Frontend MVP screens
10. Sprint 10 — End-to-end validation and product polish
11. Sprint 11 — Security, privacy, and QA hardening
12. Sprint 12 — MVP release sign-off

This sequence is designed to reduce risk by following the dependency chain:
infrastructure → core data → uploads → processing → review → approval → frontend
→ validation. For the same roadmap grouped as milestones with detailed
checklists instead of sprints, see
[`the-hub-engineering-checklist.md`](./the-hub-engineering-checklist.md); for the
full reasoning behind every decision here, see
[`the-hub-implementation-plan.md`](./the-hub-implementation-plan.md).
