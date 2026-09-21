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

## ADR-0003: The harness ships deployment artifacts for the products it builds

- **Status:** Accepted
- **Date:** 2026-09-21
- **Context:** `src/app/deploy/` contains `DockerGenerator`, `ComposeGenerator` and `CIGenerator`, and `src/app/build/verifier.py` contains `BuildVerifier`. None of the four has a caller anywhere in `src/` - a grep for the class names returns only their own definitions - and all four sat inside a coverage `omit` glob, so nothing measured that they were never called. `docs/harness-hardening-plan-part3.md` §4 raised this as a question that had to be answered before any code was written, because the two answers lead to opposite work: delete 340 lines, or fix and extend them.
- **Constraints:** What the generators emit today is insecure by default and would ship the moment they were connected: `POSTGRES_PASSWORD: password` and `MYSQL_ROOT_PASSWORD: password` in generated compose files; no `USER` directive in any of the five language branches, so every generated image runs as root; `COPY . .` placed after dependency installation, defeating layer caching; and `curl -LsSf https://astral.sh/uv/install.sh | sh` in generated CI, which pipes a script from the internet into a runner. That last one is the pattern `seeding.py` refuses `ext::` transports to prevent and `sandbox.py` refuses `python -c` to prevent, written into a file that runs on every push of the product the harness builds. Their language coverage is also narrower than the rest of the system's: four languages against the eleven the stack selector can choose.
- **Options considered:** (a) Retire them - delete the four modules and stop at a tested working tree. (b) Wire and fix them - repair the four defects, extend to every language the stack selector can choose, and connect them to the workflow. (c) Defer - leave them unwired and omitted from coverage.
- **Decision:** (b). The harness ships deployment artifacts for the products it builds. The three generators and `BuildVerifier` are to be repaired, extended and wired into the workflow.
- **Rationale:** A harness that builds a product and stops at a working tree leaves the last mile to a human, and the deployment artifacts are the part most likely to be got wrong by someone who did not write the code. The modules are individually well-made - `docker_generator.py` already produces correct multi-stage builds for five languages - so the work is repair and extension rather than design.
- **Security and privacy impact:** Net positive, but only once the work is done. Until the four defects in plan-part3 §4.1 are fixed, wiring these generators would actively ship plaintext default credentials, root containers and a `curl | sh` CI step. The defects must be fixed **before** the modules are connected to the workflow, not after; connecting first would be a regression.
- **Operational impact:** Generated products gain a Dockerfile, a compose file and a CI pipeline. The generator set becomes something that has to stay in step with the stack selector's language set, which is a standing maintenance obligation - hence the test below.
- **Consequences and trade-offs:** The plan sizes this at S-M effort, which was the estimate for *deciding*; the extension to eleven languages is days rather than hours. Option (a) was cheaper and remains the fallback if the extension proves not to be worth it. Taking (b) means the coverage `omit` entries for `deploy/*` and `build/verifier.py` in `pyproject.toml` are temporary and must be removed as each module gains a caller and a test.
- **Validation evidence:** Required before this ADR can be marked complete - a generated Dockerfile contains a non-root `USER` directive and no default password; a generated CI file contains no `curl | sh`; and one test asserts the generator language set equals the sandbox toolchain set, which is the §1-B rule (a rule defined over part of the set it governs) applied to this package so the sets cannot drift apart again.
- **Supersedes or related decisions:** None. Answers `docs/harness-hardening-plan-part3.md` §4, item 5 of its §8 backlog.

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
