# Implementation Plan

## Sprint 1 – Environment & Base Setup
**Goal:** Establish a reproducible development environment and minimal FastAPI application skeleton.

- **User Value:** Developers can quickly start coding without manual setup.
- **In‑Scope:** Dockerfile, requirements.txt, `main.py` with app instance, health endpoint.
- **Out‑of‑Scope:** Full API implementation, authentication logic.
- **Dependencies:** None.
- **Acceptance Criteria:**
  - `docker build .` succeeds.
  - Container exposes port 8000 and serves `/health` returning 200.
- **Test Strategy:** Unit test for health endpoint using TestClient.
- **Security Checks:** Verify Dockerfile uses non‑root user.
- **Documentation Work:** Update README with run instructions.
- **Risks:** None significant.
- **Rollback Notes:** If build fails, revert to previous working image.

## Sprint 2 – Intake Schema & Validation
**Goal:** Implement Pydantic `IntakeSchema` and validate incoming JSON.

- **User Value:** Clients receive clear validation errors for malformed intake payloads.
- **In‑Scope:** Define `IntakeSchema`, integrate into POST endpoint, return 422 on errors.
- **Out‑of‑Scope:** Markdown handling, persistence.
- **Dependencies:** Sprint 1.
- **Acceptance Criteria:**
  - POST with missing fields returns 400/422 with JSON detail.
  - Valid payload passes and proceeds to next step.
- **Test Strategy:** Unit tests for schema validation; integration test for endpoint error response.
- **Security Checks:** Ensure no sensitive data is logged.
- **Documentation Work:** Add API spec snippet.
- **Risks:** None.
- **Rollback Notes:** Remove schema changes if breaking existing clients.

## Sprint 3 – Directory Initialization & File Persistence
**Goal:** Create startup event to ensure `docs/intake/` exists and implement file write logic.

- **User Value:** Reliable storage of intake documents without manual directory setup.
- **In‑Scope:** FastAPI startup event, write `{id}.md` and optional `metadata.json`.
- **Out‑of‑Scope:** Content negotiation beyond Markdown.
- **Dependencies:** Sprint 2 (schema) for ID extraction.
- **Acceptance Criteria:**
  - On container start, directory is created if missing.
  - POST writes files with correct permissions.
- **Test Strategy:** Integration test checking file presence after POST.
- **Security Checks:** Verify file permissions set to 644.
- **Documentation Work:** Update README with persistence notes.
- **Risks:** Race condition on simultaneous startup; mitigated by `exist_ok=True`.
- **Rollback Notes:** Delete created files during cleanup tests.

## Sprint 4 – Optional API Key Authentication
**Goal:** Implement conditional X‑API‑KEY guard based on `INTAKE_API_KEY` env var.

- **User Value:** Secure endpoints in production without code changes.
- **In‑Scope:** Dependency that checks header, returns 401 when required.
- **Out‑of‑Scope:** OAuth2 or other auth methods.
- **Dependencies:** Sprint 3 (endpoint structure).
- **Acceptance Criteria:**
  - With env var set, missing/incorrect key yields 401.
  - Correct key grants access.
- **Test Strategy:** Integration tests with TestClient and environment variable manipulation.
- **Security Checks:** Ensure header is not logged.
- **Documentation Work:** Add auth notes to API docs.
- **Risks:** None.
- **Rollback Notes:** Remove dependency if no longer needed.

## Sprint 5 – Idempotency & Duplicate Handling
**Goal:** Treat UUID in request body as idempotency key; avoid duplicate files.

- **User Value:** Clients can retry POSTs safely without creating duplicates.
- **In‑Scope:** Check for existing `{id}.md`; if present, return 200 with same Location.
- **Out‑of‑Scope:** Conflict (409) handling or overwrite logic.
- **Dependencies:** Sprint 4 (auth), Sprint 3 (persistence).
- **Acceptance Criteria:**
  - Duplicate POST returns 200 and does not create a new file.
- **Test Strategy:** Integration test posting twice with same UUID.
- **Security Checks:** Ensure no race conditions lead to duplicate writes.
- **Documentation Work:** Update API spec on idempotency behavior.
- **Risks:** Concurrent requests could still produce duplicates; mitigated by atomic file existence check.
- **Rollback Notes:** Revert to overwrite logic if needed.

## Sprint 6 – GET Retrieval & Content Negotiation
**Goal:** Implement GET `/intakes/{id}` supporting JSON and Markdown responses.

- **User Value:** Clients can retrieve intake in preferred format.
- **In‑Scope:** Accept `Accept: application/json` or `text/markdown`; convert markdown to JSON representation if needed.
- **Out‑of‑Scope:** Advanced conversion tools.
- **Dependencies:** Sprint 5 (file storage).
- **Acceptance Criteria:**
  - GET returns 200 with requested format.
  - Unknown ID yields 404.
- **Test Strategy:** Integration tests for both formats.
- **Security Checks:** Validate no path traversal attacks.
- **Documentation Work:** Add GET endpoint docs.
- **Risks:** None significant.
- **Rollback Notes:** Remove content negotiation if too complex.

## Sprint 7 – Logging, Error Handling & Metrics Stub
**Goal:** Ensure all actions are logged and basic metrics are emitted.

- **User Value:** Observability for ops teams.
- **In‑Scope:** Python logging configuration; log request IDs; stub metric counters.
- **Out‑of‑Scope:** Full Prometheus integration.
- **Dependencies:** Sprint 6 (endpoints).
- **Acceptance Criteria:**
  - Logs contain timestamps, request ID, method, path.
  - Error paths return 500 with concise message.
- **Test Strategy:** Verify log output in tests.
- **Security Checks:** Ensure logs do not expose secrets.
- **Documentation Work:** Add logging notes.
- **Risks:** None.
- **Rollback Notes:** Disable detailed logging if performance impacted.

## Sprint 8 – Unit & Integration Test Suite Completion
**Goal:** Finalize comprehensive test coverage for all endpoints and edge cases.

- **User Value:** Confidence in reliability before release.
- **In‑Scope:** All previously defined tests plus negative cases.
- **Out‑of‑Scope:** Performance/load testing.
- **Dependencies:** All previous sprints.
- **Acceptance Criteria:**
  - Test coverage ≥90% for key modules.
  - CI pipeline passes locally.
- **Test Strategy:** Use pytest and coverage tools.
- **Security Checks:** Ensure tests do not leak sensitive data.
- **Documentation Work:** Update test README.
- **Risks:** None.
- **Rollback Notes:** Remove flaky tests if needed.

## Sprint 9 – Deployment Packaging & CI/CD Hook
**Goal:** Finalize Docker image, add basic CI workflow.

- **User Value:** Automated build and deploy pipeline.
- **In‑Scope:** Dockerfile final tweaks, GitHub Actions workflow for linting and test run.
- **Out‑of‑Scope:** Advanced deployment orchestrations.
- **Dependencies:** All previous sprints.
- **Acceptance Criteria:**
  - Docker image builds successfully on CI.
  - Tests run in CI environment.
- **Test Strategy:** Verify GitHub Actions workflow locally via act.
- **Security Checks:** Ensure no secrets are exposed in the pipeline.
- **Documentation Work:** Add deployment README.
- **Risks:** None.
- **Rollback Notes:** Revert to manual deploy if CI fails.

---

### Open Questions
1. **Future Persistence Needs** – If we anticipate scaling beyond local FS, should we abstract storage behind an interface now?
2. **Content Negotiation Extensibility** – Will we need additional formats (e.g., HTML) in the future? Should we design a pluggable converter?
3. **Logging/metrics Stack** – Do we target a specific observability stack (Prometheus, Grafana, ELK) for production use?

---

## Summary
The plan splits the implementation into nine independent sprints, each delivering user‑visible functionality and verifiable tests before proceeding to the next. This incremental approach minimizes risk while ensuring that every new feature can be validated in isolation.
