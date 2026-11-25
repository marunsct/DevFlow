# Product quality audit: the UI, database and API of what the harness builds

Date: 2026-11-25. Read-only review of eight stored products against how a strong senior engineer would build them in 2026.
Method: reading the product code, specifications, reviews and delivery notes; static checks (contrast ratios, unused style rules). Nothing was run or rendered, so every "would crash / would show" below is from reading the code.

Product paths are relative to the review copies (`<scratchpad>/products/`); harness paths are relative to the repo.

## 1. Verdict

| Layer | Meets a senior standard? | One-line reason |
|---|---|---|
| UI | **No.** Functional and accessible in the basics, visually a styled form and a list. | The owner's impression is right. The interface is built to what the tests can find (labels, roles), never to how it looks. On the medium brief the interface is not built at all. |
| Database | **No on the medium brief; adequate on the small ones.** | The specification's schema is good; the code does not follow it and no gate holds it to it. No migrations, timestamps or indexes anywhere. |
| API | **Small briefs: correct and robust, thin on design. Medium: several real bugs behind green tests.** | Status codes and validation are right where a test checks them; error shape, pagination, documented responses and authorisation errors are not checked by anything. |

The strongest single finding: **the harness builds what its acceptance suite tests, and the suite tests function only.** Everything below follows from that, plus two gates that record quality findings without enforcing them.

## 2. What was found, by product

### 2.1 Medium brief: task-management dashboard (run-bc3cbd00, sprint 2 of 3, in progress)

**UI: not built, and not planned.**
- `frontend/src/App.tsx:1-10` is one `<h1>`; there is no stylesheet, component, route or API client.
- `docs/sprint_plan.md:24,71,110-112` lists "Frontend implementation" and "Docker containerization" as **out of scope in all three sprints**. Its open question (`:139`) says why: "The acceptance criteria are all API-level tests. The frontend ... is not tested by any acceptance criterion."
- The specification has a full interface design (`docs/technical_specification.md:139-150`) and two interface criteria (AC-14 responsive, AC-15 accessibility, `:135-136`), but the locked criteria (`docs/acceptance_criteria.md`) are the brief's 13 lines, all provable through the API. The brief's "Modern web application with responsive design" sits under Requirements, not Acceptance Criteria, so it never became a criterion.
- If this run finishes all three sprints green, it delivers a "dashboard" with no dashboard.

**Database: the code does not match the adopted schema.**

| Specification (adopted, `technical_specification.md:31-35`) | Code (`backend/app/models.py`) |
|---|---|
| UUID ids | `Integer` ids (`:29,48,79`) |
| `created_at`, `updated_at` on every record | none on any table |
| `RefreshToken.token_hash` (hashed) | `token` stored in plain text (`:52`) |
| `expires_at` datetime | `Date` (`:53`), assigned a datetime (`routers/auth.py:125`), compared with `date.today()` (`:213`) |
| Category and Tag owned by a user | `name` unique for all users (`:62,71`): one person's category name blocks or is shared with everyone |
| status `pending` | `todo` (`:22`) |
| Alembic migration `001_initial.py`, indexes (DB-7) | no `alembic/` directory; no index on `owner_id`, `assignee_id`, `status`, `due_date`; tables exist only through `create_all` in the test fixture (`tests/conftest.py:35`), so the service has no way to create its schema |

The milestone review saw this and waved it through: "Checked DB-1 through DB-7 ... and SR-1, SR-6, SR-9 ... adopted by the specification but not part of the CRUD task operations scope. They are noted but do not block this milestone" (`docs/milestone_review.md`, item 6).

**API: real defects behind 51 green unit tests and 25 green acceptance tests.**

| Defect | Where |
|---|---|
| Category/tag lookup by name uses a primary-key fetch (`session.get(Category, name)`), so it never finds an existing one; the second use of a name hits the unique constraint and the catch-all handler answers 500 | `services/task_service.py:71,79` |
| Not the owner raises `PermissionError`, which the catch-all turns into 500 instead of 403; an assignee can read a task but any change is a 500 | `task_service.py:181,192,211`; `middleware.py:7-12` |
| `category` filter is accepted and ignored; the list returns only owned records, never assigned ones | `routers/tasks.py:27`; `task_service.py:139-167` |
| The rate limiter never records an attempt, so it never limits | `routers/auth.py:18-39` (no append anywhere) |
| `TaskUpdate.title` has no minimum; `{"title": null}` reaches a NOT NULL column: 500 | `schemas.py:68` |
| CORS `allow_origins=["*"]` with credentials; refresh cookie `secure=False`, `samesite="lax"` against the specification's Secure/Strict; the refresh token is also returned in the body | `main.py:12-18`; `routers/auth.py:130-138` |
| No pagination or sort on the list; analytics loads every row and counts in Python; analytics has no response model | `routers/tasks.py:23`; `task_service.py:223-248`; `routers/analytics.py:13` |
| No version prefix; one error shape `{"detail": ...}` with no code or field; unused dependencies `python-jose`, `passlib` | `main.py:22-24`; `pyproject.toml:16-17` |

What is good: layered structure (routers, services, schemas), bcrypt, refresh-token rotation, eager loading, check constraints on status and priority, cascade on the join tables. The shape is right; the content was never held to the specification.

### 2.2 fullstack-bookmarks (run-b6c5c636)

**UI** (`bookmarks/public/`): the pack's design tokens are used throughout, labels are bound, errors show inline, there is an empty state and a dark scheme. That is the best interface of the set. Gaps:
- Visually it is a bare `<h1>`, three stacked inputs and a ruled list (`index.html:10-35`): no page header or surface, no elevation, no icons, system font at default sizes, no hover or pressed state beyond opacity, no transitions except one flash.
- The flash that confirms a save is put on the **last** list item, but the list is newest-first, so the oldest bookmark flashes (`main.js:132-135`).
- A failed request or an unmapped error goes to `console.error` only; the person sees nothing (`main.js:155,159,173-174,207-211`). No loading or disabled state while a request runs.
- Errors are routed to fields by comparing the server's exact sentences (`main.js:143-152`), not by a field name in the response.
- The empty state is a `<div>` inside a `<ul>` (`main.js:19-22`); error spans are not tied to their inputs (`index.html:16,21,26`: no `aria-describedby`, no live region).
- Filtering sends a request on every keystroke (`main.js:179`).

**Storage and API** (`bookmarks/src/`): atomic write through a temporary file, UUID ids, a kept `createdAt`, encoded output. Gaps: every request re-reads and rewrites the whole file with no lock, which is safe only because the calls are synchronous (`store.mjs:70-93`); unreadable stored data is silently treated as empty and then overwritten (`store.mjs:32-35`); 400 for a missing field and 422 for an empty one with first-error-only (`routes.mjs:40-45,66`); the policy header allows inline scripts to suit the test tool (`routes.mjs:12-15`); 14 lines of the model's own deliberation left as comments in the handler (`routes.mjs:51-64`). The brief asks for none of pagination, versioning or a database, so their absence is a brief limit.

Delivery note: "No review read the product's code: the sprint was accepted at an escalation (DR-10), so no code, milestone or security review ran."

### 2.3 web-todo, plain (run-972956f5)

- Token-based, labelled, keyboard-usable, 267 lines of CSS. Same visual level as bookmarks: a form on a grey surface and bordered rows.
- **Dark scheme is broken**: the tokens declare `color-scheme: light dark`, but the title is hard-coded `#1a1a1a` (`styles.css:197`), which on the dark background `#0d1117` is a contrast of **1.09:1** - the main text is invisible. The description `#6b7280` is 3.91:1 (`:202`); white on the dark success colour is 2.85:1 (`:256`). The cause is in the specification: its interface design names raw colours ("primary text colour #1a1a1a", `docs/technical_specification.md:95`) and the builder obeyed it over the tokens.
- No empty state (the list is simply blank); phone width removes all page padding (`styles.css:73-78`, as the specification asked); filter controls carry no pressed state for assistive technology (`index.html:27-29`).
- Delivery note: no code, milestone or security review ran (accepted at an escalation).

### 2.4 web-todo, React (run-0d55d869)

- The pack's token stylesheet is never loaded: `src/main.tsx:1-9` imports nothing, and the builder wrote a parallel `App.css` of raw colours with no dark scheme.
- **The primary and filter controls are unstyled**: `App.css:75,99` style `.add-button` and `.filter-button`, but the elements carry no such class (`App.tsx:234,238-255`). They render in the browser's defaults, and the selected filter looks the same as the others.
- `outline: none` on focused inputs (`App.css:59`); white on `#4caf50` is 2.78:1 (`:204-206`); a finished title at 50% opacity is about 2.85:1 (`:169-172`).
- No form element (Enter does nothing), no empty state (the specification "explicitly defers ... any empty-state message"), a failed edit silently leaves edit mode (`App.tsx:182-190`), one 300-line component.
- **The milestone review found the unstyled controls as two Major findings and returned `changes_required`** (`docs/milestone_review.md`). The product shipped with them, `deliverable: true`. The same review's first finding asked to delete the pack's token file as dead code to get under the brief's 500 lines.

### 2.5 tasks-api (run-ec516cd8)

Correct to the brief: parameterised SQL, bcrypt, per-person scoping in the WHERE clause, 409 on a taken name, foreign keys on, WAL. Gaps:
- Tokens live in a process dictionary (`tasks_api/main.py:23`): every restart signs everyone out, a token never expires, there is no sign-out. The brief only requires that signing in works after a restart, so this passes. A secret key is generated and never used (`:112-114`).
- No index on `items(user_id)`, no timestamps, no `ON DELETE` (`:122-137`); schema created inline at start, no migration path.
- Every route sets `response_model=None` (`:385-416`), so the generated OpenAPI describes no response; blocking SQLite and bcrypt calls inside `async def` handlers; a `get_db` dependency defined and never used (`:151`); each handler duplicated as a wrapper around a second function; one 427-line file; dependencies unpinned (`requirements.txt`).
- No pagination, no item fetch by id, title unbounded: brief limits (the harness forbids limits the brief does not set).

### 2.6 notes-api: JavaScript, C#, Rust

| Product | Good | Gap |
|---|---|---|
| JS (run-031094d4) | atomic write, id validation | `src/app.js:2` imports `supertest`, a development dependency, into the product to give tests an `inject` method (`:206-229`); the Dockerfile installs with `--omit=dev`, so the container would fail at start. Ids are max+1, so a deleted last id is reused (`:118`). An empty body text is refused although the brief only requires a title (`:111-114`). A non-JSON body gets the framework's HTML error. |
| C# (run-c46d5d9a) | repository class, transactions, parameterised SQL, `Location` on create | two error shapes: `{"error"}` for 4xx and problem-details for 500 (`Program.cs:47,57`); the table is re-ensured on every connection (`SQLiteRepository.cs:45`); `body` nullable (`:16`) |
| Rust (run-59135d0b) | typed handlers, one error helper, NOT NULL columns | one connection behind a global mutex (`lib.rs:17`); 319-line single module |

These are small on purpose and they are at the level the brief asks. Their gaps are consistency and production-readiness, not design.

## 3. Brief limit or quality gap?

| Brief limit (leave alone) | Genuine gap (the harness should close it) |
|---|---|
| No pagination, versioning, auth, rate limits on notes-api, bookmarks, tasks-api | No interface built on the medium brief |
| JSON-file storage where the brief allows it | Schema in code differs from the schema the specification adopted |
| No length limits, no extra validation (hidden tests punish them) | No migrations, timestamps, indexes or ownership columns where the brief asks for "proper schema" and "migrations required" |
| One page, no routing, no component library on web-todo (500-line limit, no dependencies) | Pages that are correct but plain: no hierarchy, surface, states or feedback beyond the minimum |
| Simple token on tasks-api | Broken dark scheme, unstyled controls, failed contrast, silent failures |
| | Wrong-status errors (500 for forbidden or duplicate), ignored filters, dead rate limiter |
| | Inconsistent error shape, undocumented responses, test code in the product |

## 4. Causes in the harness

| # | Cause | Evidence |
|---|---|---|
| C1 | **Only function is tested, and the plan follows the tests.** Criteria come from the brief's Acceptance Criteria lines; a requirement outside that list ("modern responsive web application", "migrations required", "Docker") becomes no criterion, and the sprint plan scopes to criteria. | medium `sprint_plan.md:24,71,110-112,139`; hidden and quality sets (`benchmarks/*/hidden`, `*/quality`) check behaviour and robustness only |
| C2 | **Adopted specialist advice is not binding.** Its per-sprint review is "minor, never gating" and the milestone reviewer may set it aside. | `src/app/agents/advice_review.py:159,185`; medium `milestone_review.md` item 6 |
| C3 | **A run accepted at an escalation skips every code-reading review, and Major review findings do not block delivery.** | delivery notes of run-b6c5c636 and run-972956f5; run-0d55d869 shipped against `changes_required` |
| C4 | **The code reviewer is told to look only for what breaks the work order.** "Do not ask for style changes ... or tests of things no criterion asks for"; nothing asks it to compare models with the specification's domain model, or error responses with the error catalogue. | `src/app/agents/code_reviewer.py` system prompt |
| C5 | **The design tokens and the interface design do not know of each other.** The UI/UX adviser is not told the pack ships tokens, so it writes raw colours into the specification; the builder then follows the specification, or writes a second stylesheet. The tokens are also a minimum (colours, spacing, focus ring): no component styles, surfaces, elevation, states or motion. | `src/app/stacks/packs/_design.py`; `specialist_advice.py:152-165`; web-todo spec `:95`; React `main.tsx` |
| C6 | **Nobody looks at the page.** Screenshots go to the reviewer and fixer only when the model reads images; the local Qwen is not in the known families, and unknown means no. The two mechanical checks catch only "scaffold stylesheet untouched" and "wider than a phone". | `src/app/agents/page_screenshots.py`; `src/app/models/vision.py`; `src/app/analysis/interface_checks.py:89` |
| C7 | **Deliberate minimalism, rightly aimed at behaviour, also lands on presentation.** "As the brief states it, nothing added" (intake) and "nor may advice add a rule the brief does not state" protect hidden scores, but the same reflex defers the empty state and trims styling to meet a line limit. | `src/app/agents/assumptions.py:60`; `specialist_advice.py` system prompt; React spec scope |
| C8 | **Database and backend advice ask for less than the UI advice does.** The database brief names fields, types, validation; not constraints, indexes for what is filtered, timestamps, ownership, transactions or the migration path. The backend brief names operations and status codes; not one error shape, list limits, documented responses, or which error is 403 versus 404. | `specialist_advice.py:166-177` |
| C9 | **No pack for the medium stack.** FastAPI with React is a "custom stack", so it gets no tokens, no migration scaffold, no page probe. | run-bc3cbd00 `docs/reviews/sprint-1-evidence.md:23` |
| C10 | **The model's limits.** A 35B local model writes competent CSS when given tokens and a concrete design (bookmarks), and loses the thread across files (class names, spec versus code). This is why checks must be mechanical or enforced, not requested. | bookmarks versus React web-todo |

## 5. How to close the gap

All items are stack-agnostic; stack specifics only in packs. "Always on" follows the owner's policy for quality changes; "switch" marks the doubtful ones until measured.

| Item | What | Where | Size | Measured by | On/switch | Risk to small benchmarks |
|---|---|---|---|---|---|---|
| **PQ.1** | **Every requirement becomes a criterion or a recorded exclusion.** Number the brief's Requirements and Technical Constraints as well as its Acceptance Criteria; a requirement with no criterion (an interface, migrations, a container) gets one, or an explicit "not built" in the delivery notes. A product whose brief asks for an interface cannot be planned with the interface out of scope in every sprint. | `app/acceptance/criteria.py`, sprint planner check, delivery notes | M | medium brief: interface files exist and a page criterion passes; count of brief requirements with no criterion = 0 | always on | Low: small briefs already list everything as criteria. Adds a sprint to medium briefs. |
| **PQ.2** | **Schema conformance check, mechanical.** After each sprint, compare the specification's domain model (record names, field names, required/unique, id kind) with what the code declares; a difference is a defect to the builder, not a note. Start with field presence and names, which need no parser per language: search the data-layer files for each adopted field. | new `app/analysis/schema_conformance.py`, called where `advice_review` runs | M | fields adopted but absent, per run (should fall to 0); medium run would have raised about 12 | always on | Low; small briefs have 3-field records. A few minutes per sprint. |
| **PQ.3** | **Adopted advice that is due is binding.** A `not_built` item whose id the sprint's work orders named is major, not minor; the milestone reviewer may defer it only to a named later sprint, and the last sprint cannot defer. | `advice_review.py:159-185`, `milestone_reviewer.py` | S | count of adopted items unbuilt at release | always on | Medium: more fix rounds. Watch minutes to green on web-todo and bookmarks. |
| **PQ.4** | **Review findings survive an escalation.** When a sprint is accepted at an escalation, still run the code review once (read-only, no gating) and carry Major findings into one bounded fix pass and the delivery notes. A product with open Major findings is delivered as "delivered with known defects", not plain "completed". | `graph/workflow.py` escalation path, release notes | M | runs shipped with a Major finding open and unflagged = 0 | always on | Adds one review stage to escalated runs only. |
| **PQ.5** | **Mechanical interface checks, added to the existing two.** (a) every class and id a stylesheet styles is used by the markup, and the reverse for state classes; (b) contrast of each text/background pair in both colour schemes, from the page probe's computed styles; (c) a raw colour in a stylesheet that declares tokens; (d) the scaffold stylesheet is still loaded by the page; (e) a focus outline removed with no replacement. Each is a defect with file and line. | `app/analysis/interface_checks.py`, `app/acceptance/page_probe.py` | M | defects found per run; all four found on the stored products (1.09:1 title, unstyled controls, unloaded tokens, `outline: none`) | always on | Low: checks are fast; fixes are small. Could cost one fix round. |
| **PQ.6** | **Tell the UI/UX adviser and the architect what the pack already gives.** The advice request names the token names and says the interface design refers to them, never to raw values; the tokens are excluded from any line limit the brief sets. | `specialist_advice.py` request builder, `brief_constraints.py` | S | raw colours in `interface_design` = 0; token file imported in every web product | always on | None expected. |
| **PQ.7** | **A fuller base stylesheet in the packs.** Extend the tokens with a small layer of unclassed element styles: page surface and header, form controls with hover, focus, disabled and invalid states, a primary and a quiet control style, a list row, an empty-state block, a message area, elevation and one transition. Element selectors only, so a builder gets a designed page by writing plain markup. | `app/stacks/packs/_design.py` (packs only) | M | PQ.10 score before and after on web-todo, web-todo-react, bookmarks | always on (it is a default the product may change) | Line-limit briefs: exclude scaffold lines (PQ.6). Run `verify_packs` on every web pack. |
| **PQ.8** | **Interface states as criteria, not prose.** For a product with a page, the specification's interface design must name what is shown when there is nothing yet, while a request is in flight, and when one fails; each becomes a line the acceptance suite can find (a role and a text). Presentation only: it adds no rule that refuses anything, so it does not conflict with "nothing added". | `specialist_advice.py` ui_ux text, `specification_parts.py`, plus a prompt-rule test with the banned words | S | products with empty, busy and failure states present (page probe finds them) | switch until measured on two families | Medium: the hidden web tests assert on list contents; an empty-state element inside the list could be counted as an item. Require it outside the list. |
| **PQ.9** | **Data and service quality bars in the advice texts.** Database: constraints the data implies (required, unique within an owner, references with a delete rule), an index for every field the interface filters or sorts on, created and changed times, how the schema is created and changed from version to version. Backend: one error shape for every failure, the difference between "not yours" and "not there", a bound on every list, every response described in the generated documentation, no test helper in product code. Each stays inside "adds no rule that refuses what the brief allows". | `specialist_advice.py:166-177`; code reviewer gets the matching five checks | S | per-run counts from PQ.2 plus a static pass: error shapes in use, lists without a bound, test imports under the product source | switch until measured (advice changes specifications) | Medium: a 3-field notes service may gain timestamps the hidden tests do not expect in responses. State that stored fields the brief does not list are never returned. |
| **PQ.10** | **A quality score, so any of the above can be measured.** Per run, from the stored product, no model needed: interface (PQ.5 counts, states present, token use, phone overflow), data (adopted fields built, constraints, indexes, migration present when asked), service (wrong-status errors found by a fixed probe set: forbidden, duplicate, malformed, unknown id; error-shape count; documented responses). Report beside hidden and quality scores in the product review. | `scripts/loop` scorer, `benchmarks/*/quality` | M | it is the measure | always on (measurement only) | None: it does not gate. |
| **PQ.11** | **Eyes on the page.** Measure whether the served model reads images (the capability probe exists); if not, allow a second, small vision model for the screenshot review only, or give a text-only reviewer the page probe's layout facts (element boxes, computed sizes, colours) in place of pictures. | `app/models/vision.py`, `page_screenshots.py`, `page_probe.py` | M | design findings raised per run; PQ.10 interface score | switch (needs a second model or a larger request) | Time: one extra request per sprint. The owner's model settings are not changed by this; a second model is an owner decision. |
| **PQ.12** | **Packs for the common full stacks.** A pack for a Python service with a built single-page interface, with the tokens, a migration tool wired to the embedded database, and a container file; the same for the Node equivalent. | `app/stacks/packs/`, `seed.py` | L | medium brief: scaffold proves, migration applies, page probe runs | always on once verified | None for small families; `verify_packs` before use. |

### Suggested order

1. **PQ.10** first (S-M, no risk): without a score, nothing else can be kept or parked under the Measure/Fix rule.
2. **PQ.1, PQ.2, PQ.3, PQ.4**: these close the medium-brief gaps and are enforcement, not taste. PQ.1 alone decides whether a medium product has an interface.
3. **PQ.5, PQ.6, PQ.7**: the visual floor for every web product, with no dependence on the model's eye.
4. **PQ.8, PQ.9** behind switches, measured on two runs per family.
5. **PQ.11, PQ.12** when the above have moved the score.

### Filed for the Fix batch (found while reading, not part of the plan above)

- The pack's token stylesheet counts against a brief's line limit, so a reviewer asked for its removal (run-0d55d869 milestone review).
- A product imported a development-only package in its source while its container installs without them (run-031094d4): a static check of product imports against the runtime dependency list would catch it in any language with a manifest.
- Model deliberation left as comments in product code (run-b6c5c636 `routes.mjs:51-64`).

## 6. Limits of this audit

- Nothing was executed or rendered; contrast figures are computed from the declared colours, and behaviour claims are from reading.
- The medium run is in progress; its schema and API findings describe sprint 2's state and some may be due in sprint 3. The interface and container being out of scope in all three sprints is from the plan itself.
- Whether the served model reads images was not measured here (C6 rests on the name-based default in `vision.py`).
- The Rust and C# services were sampled, not read in full.
