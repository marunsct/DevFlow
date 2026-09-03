# The Hub Tools And Models Plan

**Status:** Draft for review  
**Source document:** `.github/Detailed viability and product info.docx`  
**Date:** 2026-09-03

This is the first Step 1 output for the supplied example product. It is intentionally proposed, not approved. Future products must create this document from `docs/tools-and-models-template.md` rather than copying these choices.

## MVP Tool Inventory

| Area | Proposed choice | Alternative considered | Reason for proposal | Validation |
|---|---|---|---|---|
| Web UI | Next.js with TypeScript | React SPA, server-rendered alternative | The product needs recording UI, authenticated views, responsive workflows, and typed contracts | Build a recording and thread-review flow |
| Styling and components | Existing team design system or Tailwind only if absent | Component library | Avoid duplicate primitives while keeping accessible states consistent | Accessibility and responsive UI tests |
| API | NestJS with TypeScript and OpenAPI | FastAPI-only, Go service | Modular boundaries fit auth, threads, approvals, uploads, and integrations | Contract and authorization tests |
| Database | PostgreSQL with Prisma | MySQL, document database | Relational tenant, approval, audit, and lifecycle invariants are central | Migration and isolation tests |
| Object storage | S3-compatible storage, MinIO locally | Filesystem, provider-specific blob API | Direct browser uploads and portable deployment semantics | Pre-signed upload and expiry test |
| Jobs | Redis with BullMQ | In-process jobs, managed queue | Video and AI work must be asynchronous, retryable, and observable | Idempotency and retry tests |
| AI service | FastAPI adapter service | AI logic inside API | Keeps model runtime replaceable and isolates long-running inference | Stubbed contract tests and failure tests |
| Auth | Product-selected OIDC provider, development stub only locally | Custom authentication | Avoid custom credential security; provider remains an open product decision | Login, role, and tenant tests |
| Observability | Structured logs, metrics, OpenTelemetry, LangSmith for LangChain/LangGraph paths | Logs only | Queue and AI behavior needs traceable latency and failure evidence | Correlation and trace checks |
| Testing | Unit, integration, API contract, browser E2E, accessibility, security regression | Manual testing only | Workflow state and tenant boundaries are too risky for manual-only checks | CI test suite and review evidence |

## MVP Model Inventory

| Model role | Proposed choice | Local or hosted | Reason for proposal | Fallback and validation |
|---|---|---|---|---|
| Transcription | Whisper-compatible service/model | Local LM Studio-compatible or dedicated worker; hosted optional | Product requires recorded-video transcription and timestamped segments | Validate word/segment timestamps, language support, latency, and privacy |
| Summarization | Configurable LangChain model adapter | LM Studio for development; hosted provider only with explicit data approval | Keeps prompts and model providers replaceable | Compare representative transcripts against quality rubric |
| Action extraction | Structured-output LangChain model adapter | LM Studio first; hosted fallback optional | Action items need a stable schema and human review | Contract tests, malformed-output tests, human acceptance flow |
| Embeddings | Deferred for MVP unless keyword search is insufficient | Local or hosted must be decided later | Semantic search is explicitly deferred in the product brief | ADR and retrieval experiment before adding a vector dependency |
| Evaluation | Deterministic fixtures plus LangSmith evaluator when credentials are available | Local tests and optional LangSmith | Avoid silently trusting AI output and preserve the repository's LangSmith workflow | Inspect real outputs and traces before extraction/evaluation code |

## Current Local Development Configuration

- `OPENAI_BASE_URL=http://localhost:1234/v1` points the OpenAI-compatible LangChain adapter at LM Studio.
- `OPENAI_API_KEY=lm-studio` is a local placeholder accepted by LM Studio; it is not a production credential.
- `OPENAI_MODEL` must match the model loaded in LM Studio.
- `LANGSMITH_ENDPOINT` and `LANGSMITH_API_KEY` are used only when LangSmith tracing is enabled.

## Decisions Required Before Approval

1. Select and benchmark the supported transcription implementation.
2. Define the structured schemas for summary and action extraction.
3. Choose the production model provider and data-processing region.
4. Decide whether local inference is a supported production deployment or development-only.
5. Define quality, latency, context-size, cost, timeout, retry, and fallback thresholds.
6. Confirm licensing and data rights for every model and dataset.
7. Record accepted choices as ADRs before adding production dependencies.

## Approval Status

**Not approved.** The Tools and Models Architect and Senior Architect Reviewer must validate the alternatives, experiments, privacy controls, and contracts before implementation proceeds.
