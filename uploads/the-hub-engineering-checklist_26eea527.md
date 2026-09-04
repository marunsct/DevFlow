# The Hub: Milestone-by-Milestone Engineering Checklist

This checklist breaks the work into sequential milestones so the team builds only
the next layer of the system when the previous layer is verified.

> **New here?** Read [`the-hub-glossary.md`](./the-hub-glossary.md) first for
> plain-English definitions of every tool and term used below. The full reasoning
> behind every decision here — the data model, API design, and architecture — lives
> in [`the-hub-implementation-plan.md`](./the-hub-implementation-plan.md); this
> checklist is the condensed "do this, then check it off" version of that plan.
> If anything here ever seems to contradict the implementation plan, the
> implementation plan is correct — this file should be updated to match it.

---

## Milestone 1 — Local environment and infrastructure

### Goal
Get the local development stack running reliably: three background services
(database, cache/queue, file storage) all running in Docker containers and
reachable from your machine.

### Checklist
- [ ] Confirm Linux base environment is ready
  - [ ] Ubuntu LTS installed
  - [ ] Node 20 installed (`node -v` should print `v20.x.x`)
  - [ ] Python 3 installed (`python3 --version`)
  - [ ] Git configured (`git config --global user.name` / `user.email` set)
- [ ] Install Docker and Docker Compose
  - [ ] Docker engine working (`docker --version`)
  - [ ] `docker compose version` works
- [ ] Start infrastructure services
  - [ ] `cd infra && docker compose up -d`
  - [ ] Postgres running
  - [ ] Redis running
  - [ ] MinIO running
- [ ] Validate connectivity (exact commands — see
      [`the-hub-implementation-plan.md` §8.3](./the-hub-implementation-plan.md#83-local-validation--the-exact-commands)
      if any of these fail)
  - [ ] `docker exec hub-postgres pg_isready -U postgres` → `accepting connections`
  - [ ] `docker exec hub-redis redis-cli ping` → `PONG`
  - [ ] MinIO console opens at `http://localhost:9001` (login `minioadmin` /
        `minioadmin`)
- [ ] Record environment values in `.env` files and shared notes (create these
      from a checked-in `.env.example` — never commit the real `.env`)
  - [ ] database URL — `postgresql://postgres:postgres@localhost:5432/hub`
  - [ ] Redis URL — `redis://localhost:6379`
  - [ ] MinIO credentials — `minioadmin` / `minioadmin` (local dev only)

### Definition of done
- Local infrastructure is healthy and repeatable.
- Every developer can bring the stack up with a single command
  (`docker compose up -d` from `infra/`).

---

## Milestone 2 — Backend foundation

### Goal
Have the NestJS API booting and connected to Postgres, Redis, and MinIO — no
business logic yet, just proving the four programs can talk to each other.

### Checklist
- [ ] Initialize NestJS app in `backend/core-api` *(already scaffolded in this
      repo — confirm `npm run start:dev` works before adding anything new)*
- [ ] Install core dependencies *(already present in `package.json` — verify with
      `npm ls @nestjs/config @nestjs/swagger @nestjs/bullmq bullmq ioredis prisma
      @prisma/client @aws-sdk/client-s3`)*
  - [ ] `@nestjs/config`
  - [ ] `@nestjs/swagger`
  - [ ] `@nestjs/bullmq`
  - [ ] `bullmq`
  - [ ] `ioredis`
  - [ ] `prisma`
  - [ ] `@prisma/client`
  - [ ] `@aws-sdk/client-s3`
- [ ] Configure environment variables (add these to
      `backend/core-api/.env.example`, then copy to a local `.env`)
  - [ ] `DATABASE_URL`
  - [ ] `REDIS_URL`
  - [ ] `MINIO_ENDPOINT`
  - [ ] `MINIO_ACCESS_KEY`
  - [ ] `MINIO_SECRET_KEY`
  - [ ] `JWT_SECRET`
- [ ] Create the Prisma schema for core entities — use the exact schema in
      [`the-hub-implementation-plan.md` §9.1](./the-hub-implementation-plan.md#91-domain-model-canonical-prisma-schema),
      don't improvise field names:
  - [ ] `Workspace`
  - [ ] `User` (with `Role` enum: `ADMIN` / `CONTRIBUTOR` / `REVIEWER` / `GUEST`)
  - [ ] `Thread` (with `ThreadStatus` enum — see implementation plan §5.1)
  - [ ] `Attachment`
  - [ ] `Comment`
  - [ ] `Approval` (with a `@@unique([threadId, userId])` constraint)
- [ ] Run the initial migration: `npx prisma migrate dev --name init`
- [ ] Generate the Prisma client: `npx prisma generate`
- [ ] Add base NestJS modules
  - [ ] app module
  - [ ] auth module
  - [ ] threads module
  - [ ] uploads module
  - [ ] queue module
- [ ] Add Swagger setup for API docs (visit `/api` or `/docs` once wired up to
      browse every endpoint from a web page — very useful for testing without a
      frontend)
- [ ] Verify backend boots with `npm run start:dev`, with no startup errors in
      the terminal

### Definition of done
- API starts without errors.
- Prisma schema is migrated and usable (`npx prisma studio` opens a browsable
  view of your database tables — a good sanity check).
- The backend can talk to Postgres and Redis.

---

## Milestone 3 — Thread domain and CRUD APIs

### Goal
Create the primary business object and the first real product flow: a user can
create a thread and read it back through the API.

### Checklist
- [ ] Confirm `Thread` fields match the canonical schema (implementation plan
      §9.1) — `id`, `title`, `description`, `status`, `workspaceId`, `creatorId`,
      `createdAt`, `updatedAt`, plus `transcript`/`aiSummary` (filled in later by
      the AI worker, Milestone 6)
- [ ] Implement thread creation API — `POST /api/v1/threads`
- [ ] Implement thread list API — `GET /api/v1/threads`
- [ ] Implement thread detail API — `GET /api/v1/threads/:id`
- [ ] Implement thread update API — `PATCH /api/v1/threads/:id`
- [ ] Implement basic validation rules (a NestJS DTO with `class-validator`
      decorators is the standard way to do this — see the glossary's "DTO" entry)
  - [ ] title required
  - [ ] creator required
  - [ ] workspace required
- [ ] Add API error handling
  - [ ] `400` validation errors
  - [ ] `404` not found
  - [ ] `401`/`403` auth checks
- [ ] Add DTOs for the create/update flow
- [ ] Verify the thread API with manual requests (Postman, Insomnia, `curl`, or
      the Swagger page from Milestone 2) — create a thread, list threads, fetch
      one by ID, and confirm a request missing `title` returns `400`

### Definition of done
- A user can create and fetch a thread via API.
- Core thread data is persisted in PostgreSQL (spot-check with
  `npx prisma studio`).

---

## Milestone 4 — Upload and object storage workflow

### Goal
Support recording and media upload without putting large files through the API
server — see
[the upload flow diagram in the implementation plan §9.4](./the-hub-implementation-plan.md#94-upload-flow)
for why this is a 3-step handoff instead of a single "upload file" endpoint.

### Checklist
- [ ] Add MinIO client configuration (`@aws-sdk/client-s3`, pointed at the local
      MinIO endpoint from Milestone 2's `.env`)
- [ ] Implement the presigned upload URL endpoint —
      `POST /api/v1/threads/:id/upload-url` (request/response shapes are in
      implementation plan §9.3)
- [ ] Implement the upload confirmation endpoint —
      `POST /api/v1/threads/:id/confirm-upload`
- [ ] Store attachment metadata in the database (the `Attachment` model from
      Milestone 2)
  - [ ] object key (`storageKey`)
  - [ ] file name
  - [ ] mime type
  - [ ] size
  - [ ] `threadId`
  - [ ] `status` (`UPLOADING` / `READY` / `FAILED`)
- [ ] Validate upload ownership and thread access (only someone who can access
      the thread should be able to request an upload URL for it)
- [ ] Restrict file types and max size (e.g. only `video/webm`, `video/mp4`;
      reject anything above a size limit you pick, such as 500 MB, before issuing
      a presigned URL)
- [ ] Add basic upload failure handling (if the browser's direct-to-MinIO `PUT`
      fails partway, the attachment should stay `UPLOADING`/`FAILED`, not silently
      look like it succeeded)
- [ ] Confirm a file can be retrieved from MinIO after upload — open the MinIO
      console (`http://localhost:9001`) and verify the object exists at the
      expected `storageKey`

### Definition of done
- A user can upload a file to the system and the backend records metadata
  correctly.
- MinIO is storing media objects for later processing.

---

## Milestone 5 — Queue and async job processing

### Goal
Move AI and processing work out of the request path, so confirming an upload
returns instantly instead of waiting for transcription to finish.

### Checklist
- [ ] Configure BullMQ with Redis (`@nestjs/bullmq`, pointed at `REDIS_URL`)
- [ ] Create the `video-processing` queue
- [ ] Enqueue a processing job after upload confirmation (one line inside the
      `confirm-upload` service method — see implementation plan §9.5 for the
      exact producer/consumer code shape)
- [ ] Create the job worker/consumer (a `@Processor('video-processing')` class)
- [ ] Add status updates on job progress, reflected on the `Thread.status` field
  - [ ] queued (thread is `PROCESSING`)
  - [ ] processing
  - [ ] succeeded (thread moves to `IN_REVIEW`)
  - [ ] failed (thread stays visible with a clear "processing failed" state —
        never leave it stuck silently)
- [ ] Add a retry strategy for failed jobs (BullMQ supports this via job options,
      e.g. `attempts: 3` with exponential backoff)
- [ ] Ensure jobs are idempotent where possible — running the same job twice
      (e.g. after a retry) shouldn't create duplicate data (see glossary
      "Idempotent")
- [ ] Test queue processing with a sample artifact — upload a short test video
      and confirm the job actually runs (check `docker exec hub-redis redis-cli`
      or add a `console.log`/logger line in the consumer while testing)

### Definition of done
- Background jobs execute asynchronously.
- Thread status changes reflect processing state.

---

## Milestone 6 — AI worker integration

### Goal
Process uploaded media into a transcript and an AI-generated summary.

### Checklist
- [ ] Scaffold a Python service in `ai-worker/`
- [ ] Create a virtual environment: `python3 -m venv .venv && source
      .venv/bin/activate`
- [ ] Install dependencies (`pip install -r requirements.txt` once the file
      below exists)
  - [ ] `fastapi`
  - [ ] `uvicorn`
  - [ ] `httpx`
  - [ ] `pydantic`
  - [ ] `minio`
  - [ ] `openai-whisper`
- [ ] Implement a FastAPI endpoint for processing — matches the input contract in
      implementation plan §10.2 (`{ "storageKey": "...", "threadId": "..." }` in,
      `{ "transcript": "...", "summary": {...} }` out)
- [ ] Download the object from MinIO using `storageKey`
- [ ] Extract audio from the uploaded video (e.g. with `ffmpeg`)
- [ ] Run speech-to-text transcription with Whisper
- [ ] Send the transcript to an LLM for summary generation, using the strict
      JSON-output system prompt in implementation plan §10.3
- [ ] Return structured JSON containing
  - [ ] transcript
  - [ ] summary
  - [ ] key points
  - [ ] action items
  - [ ] risk level
- [ ] Handle failure cases cleanly
  - [ ] no audio track found
  - [ ] file corrupt / unreadable
  - [ ] LLM unavailable or returned invalid JSON (validate before saving — see
        implementation plan §10.3)
- [ ] Confirm results are stored back into the thread (via the backend's queue
      consumer from Milestone 5, or a webhook callback — pick one pattern and use
      it consistently)

### Definition of done
- Uploaded media is processed into usable AI output.
- Transcript and summary are available for review in the thread.

---

## Milestone 7 — Comments and review workflow

### Goal
Let users discuss the decision as part of a review thread.

### Checklist
- [ ] Define the comment model (already in the canonical schema, Milestone 2)
  - [ ] `threadId`
  - [ ] `authorId`
  - [ ] `content`
  - [ ] `timestampSeconds` (optional — links a comment to a moment in the video)
  - [ ] `createdAt`
- [ ] Implement the comment create endpoint — `POST /api/v1/threads/:id/comments`
- [ ] Implement the comment list endpoint (or include comments in the thread
      detail response from Milestone 3 — either works, pick one and be
      consistent)
- [ ] Add validation for empty comments (reject blank/whitespace-only content
      with `400`)
- [ ] Add sorting by creation time (oldest first is the usual convention for a
      discussion thread)
- [ ] Show comments in UI with author info

### Definition of done
- Users can leave comments tied to the decision thread.
- The comment timeline is usable and readable.

---

## Milestone 8 — Approval workflow

### Goal
Turn the thread into a real decision resolution flow, using the canonical
7-status lifecycle from
[implementation plan §5.1](./the-hub-implementation-plan.md#51-decision-states-canonical).

### Checklist
- [ ] Define the approval model (already in the canonical schema, Milestone 2)
  - [ ] `threadId`
  - [ ] `userId`
  - [ ] `decision` (`APPROVED` / `REJECTED`)
  - [ ] `createdAt`
- [ ] Implement the approval API
  - [ ] `POST /api/v1/threads/:id/approve`
  - [ ] `POST /api/v1/threads/:id/reject`
- [ ] Add thread status transitions (exact rules, matching the state diagram in
      implementation plan §5.1)
  - [ ] `IN_REVIEW → APPROVED` on the first approval (MVP rule: any one approval
        resolves it — no multi-approver policy engine needed yet)
  - [ ] `IN_REVIEW → REJECTED` on any rejection
  - [ ] `APPROVED`/`REJECTED` → `REOPENED` when someone reopens it
  - [ ] `REOPENED → IN_REVIEW` once it's back under active discussion
- [ ] Prevent duplicate approvals from the same user — enforced at the database
      level by the `@@unique([threadId, userId])` constraint on `Approval`; also
      return a friendly `400`/`409` from the API instead of a raw database error
- [ ] Add records for approval history (the `Approval` rows themselves *are* the
      history — just make sure they're never deleted, only added)
- [ ] Add UI buttons for approve/reject actions
- [ ] Add tests for approved and rejected states

### Definition of done
- A decision can be formally approved or rejected.
- The system stores an auditable approval record.

---

## Milestone 9 — Frontend foundation

### Goal
Build the screens needed to use the product end-to-end.

### Checklist
- [ ] Initialize a Next.js app in `frontend/`: `npx create-next-app@latest
      frontend --typescript --tailwind`
- [ ] Configure Tailwind and TypeScript *(the command above sets both up by
      default)*
- [ ] Add an API base URL config (e.g. `NEXT_PUBLIC_API_URL` in
      `frontend/.env.local`, pointing at `http://localhost:3000` or wherever the
      backend runs)
- [ ] Build app shell and layout
- [ ] Create thread list page (`/threads`)
- [ ] Create new thread page (`/threads/new`)
- [ ] Create thread detail page (`/threads/:id`)
- [ ] Add upload flow in UI (wires up the recording hook and upload routine from
      implementation plan §9.4/§11.3)
- [ ] Add loading and empty states (what does the page look like before any
      threads exist, or while a request is in flight?)
- [ ] Add error handling for failed requests (what does the page show if the API
      is unreachable or returns an error?)
- [ ] Connect the frontend to backend APIs

### Definition of done
- A user can create a thread and see it in the interface.
- Thread data from the backend loads into the UI.

---

## Milestone 10 — Frontend decision and review UX

### Goal
Make the product usable and understandable from a user standpoint.

### Checklist
- [ ] Add transcript panel
- [ ] Add AI summary panel
- [ ] Add comment input form
- [ ] Add video or attachment preview
- [ ] Add status badges for thread state (all 7 values from implementation plan
      §5.1, each with a distinct color — e.g. gray for `DRAFT`, blue for
      `PROCESSING`/`IN_REVIEW`, green for `APPROVED`, red for `REJECTED`)
- [ ] Add approver list and status indicators
- [ ] Add approve/reject action buttons
- [ ] Add success/error messaging
- [ ] Add route guards or auth placeholders if needed
- [ ] Validate UX on a complete thread lifecycle (walk through
      draft → processing → in review → approved yourself, clicking through the
      real UI, not just the API)

### Definition of done
- A user can complete the end-to-end decision flow using the UI.
- The page clearly communicates thread status, review context, and decision
  outcome.

---

## Milestone 11 — Real-time updates and notifications

### Goal
Improve responsiveness after the core flow works. Default to polling — see
implementation plan §12 for why this is a legitimate MVP choice, not a shortcut.

### Checklist
- [ ] Decide between polling vs SSE/WebSockets — **default to polling for MVP**
- [ ] Add a thread status refresh flow (re-fetch `GET /threads/:id` every few
      seconds while status is `PROCESSING`)
- [ ] Notify UI when processing completes (stop polling once status leaves
      `PROCESSING`)
- [ ] Notify UI after approval or rejection
- [ ] Add a simple notification list or banner
- [ ] Validate update behavior during processing (start a real upload and watch
      the UI update without a manual page refresh)

### Definition of done
- Users see thread state changes without manual refresh.

---

## Milestone 12 — Security, privacy, and quality checks

### Goal
Ensure the MVP is safe enough for internal testing. Full detail in
[implementation plan §13](./the-hub-implementation-plan.md#13-security-and-hardening).

### Checklist
- [ ] Validate authorization on all thread endpoints (every single one — it's
      easy to secure the obvious ones and forget a newer endpoint added later)
- [ ] Restrict ownership for uploads and approvals
- [ ] Apply file type and file size validation (Milestone 4)
- [ ] Add CSP (Content Security Policy) headers for the frontend
- [ ] Validate URLs and embed safety (only relevant if the live-prototype-embed
      feature was built — see implementation plan §13's `PrototypeEmbed` example)
- [ ] Review data retention requirements (how long do videos/transcripts stay
      stored? document the decision even if the answer for MVP is "indefinitely")
- [ ] Add a PII redaction note or review process for transcript content (full
      automated redaction is post-MVP — see implementation plan §17 — but at
      minimum, document that transcripts may contain sensitive spoken content)
- [ ] Add logging for key actions (thread created, approved, rejected — enough to
      answer "who did what, when" later)
- [ ] Run end-to-end smoke tests
- [ ] Fix edge cases discovered in manual validation

### Definition of done
- The app can be used internally without obvious privacy or access issues.
- The primary user flow works reliably.

---

## Milestone 13 — MVP release readiness

### Goal
Prepare the project for a real user validation release.

### Checklist
- [ ] Run a full smoke test for
      create → upload → process → review → approve/reject
- [ ] Verify backend and frontend both work with the Docker stack
      (`docker compose up -d` from a completely clean checkout)
- [ ] Confirm env variables are documented (every `.env.example` file is
      up to date and matches what the code actually reads)
- [ ] Confirm startup instructions are clear (a new team member should be able to
      follow §7–§9 of the implementation plan and get the app running with no
      undocumented steps)
- [ ] Review the backlog and remove non-MVP items (anything from implementation
      plan §17 that snuck into scope — cut it, don't build it now)
- [ ] Validate all key user flows on a fresh setup
- [ ] Capture known issues and next-phase backlog
- [ ] Sign off on MVP scope

### Definition of done
- The product is ready for user validation with a focused, working workflow.
- The team can identify the next post-MVP features (implementation plan §17)
  without scope drift.

---

## Suggested execution order

1. Infrastructure
2. Backend foundation
3. Thread CRUD
4. Upload and storage
5. Queue and async jobs
6. AI worker
7. Review comments
8. Approval flow
9. Frontend pages
10. UX flow completion
11. Notifications
12. Security and quality checks
13. MVP release sign-off

This order keeps the product build focused and reduces the risk of building the
wrong layer too early. For the same roadmap broken into time-boxed sprints
instead of milestones, see
[`the-hub-sprint-breakdown.md`](./the-hub-sprint-breakdown.md); for the full
reasoning behind every decision here, see
[`the-hub-implementation-plan.md`](./the-hub-implementation-plan.md).
