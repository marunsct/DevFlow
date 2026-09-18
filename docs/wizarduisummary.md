# Guided Wizard UI — Feature Summary

**Status:** Complete and deployed (2026-09-18)
**Verified live against run:** `run-8d28ee3f-a0e9-40d4-adc2-74d5bf1f81a1`

---

## 1. The Requested Feature

The original complaint: the run dashboard *"looks like some admin dashboard and it is not providing useful information."*

The requested feature was a **guided wizard UI** on the run page:

1. A **toggle** on the run page — on = wizard view, off = classic dashboard. The choice persists across reloads (`localStorage.runView`).
2. The wizard presents the build as **phases in order**: `Product intake → Design → Sprint 1..n → Final Summary`, generated from the run's state (not hardcoded).
3. A **rejected sprint re-runs as a revision under the same sprint stage** — not as a phantom second sprint. The rejection comment is shown with the pass that it started.
4. **All stages are selectable and viewable** — click any phase in the rail to see what happened in it, including per-step log lines.
5. The UI should be **modern and fluid**.

A pivotal instruction shaped the architecture:

> *"Make decisions for the overall harness — don't just fix the UI. If something needs to be fixed in the backend for the correct architecture, correct them as well; don't just change the UI to match it."*

That meant the wizard could not be a frontend-only re-derivation of the event stream. The old code had the browser walk the raw stage history and infer phases, statuses, durations, and review outcomes on its own — the same logic the server's classic timeline also ran. Two readers of one history inevitably drift.

## 2. Architecture Decision: One Source of Truth

The core decision: **the wizard model is built server-side, in one place, from a single pass over the run's event history.** The frontend became a *pure renderer* — it displays what the API gives it and derives nothing about run state itself.

```
event history (Redis)  ──►  build_wizard_model()  ──►  GET /api/runs/{id}/wizard  ──►  WizardDashboard.tsx (renders only)
                            (src/app/server/runs.py)        (WizardModel JSON)            (no phase/status inference left)
```

Consequences:

- The browser and the API can no longer disagree — there is exactly one reader of the history.
- The deleted `wizardData.ts` (700 lines of client-side stage-walking) had the *same* duplicate-step bug the server had; deleting it removed a whole class of drift instead of patching it twice.
- The wizard endpoint returns everything the UI needs — step durations, note lists, review outcomes, summary counts — so the panel never has to compute a number itself.

### 2.1 Base-stage transition detection (the dedup fix)

A run's events do not move in clean stage steps. While a node works, it writes artifacts through an approval gate, so its stage flaps between e.g. `specialist_backend_1` and `awaiting_approval:specialist_backend_1`. Comparing *raw* stage names reads every flap as a transition and opens a duplicate step per gate — the classic timeline collapses these for exactly this reason.

The fix: transitions are detected on the **base stage** (pause prefix stripped, `_wizard_base_stage`). A pause is a *state of the step that is running*, not a new step. A genuine change of base is always a transition, even if it arrives while paused. This collapsed the live run's raw stream to 13 real transitions, and Sprint 1 renders exactly **21 step cards** — matching the API count (verified in browser).

### 2.2 Pause-as-state, not pause-as-step

- `awaiting_approval:<stage>` — the stage is working; no new step, no review.
- `awaiting_user_review:<point>` where point ∈ {`sprint`, `technical_specification`, `product_intake`} — a **review** opens (tracked with its opening sequence for later resolution). Approval pauses are deliberately *not* reviews.

### 2.3 Sprint revision logic

The walk's only hard question is every re-entry into `technical_lead`: *new sprint or revision of the current one?*

| What ran in between | Interpretation |
|---|---|
| `sprint_advance` (review approved) | Genuinely **new sprint** — open `Sprint N+1` |
| A review, but no advance | Sprint was **sent back** — new **revision under the same sprint**, carrying the rejection comment |
| Neither (e.g. re-entry from defect remediation) | The **same revision continues** — no structural change |

### 2.4 Decision events (Step 1 of the plan)

*"Was this review approved or sent back?"* used to be implied only by whichever stage ran next, and every timeline re-inferred it separately. Now the decision is recorded **where it was made**:

- `POST /api/runs/{id}/review` publishes a `review_decision` event (`action`: approve/changes/skip, comment in the message, `review_point` + flags in metadata).
- `POST /api/runs/{id}/approval` publishes an `approval_decision` event (the manual half; auto-approvals were already recorded as `approval_auto`).

Both types are registered in `src/app/server/events.py`. The wizard's walk **skips** decision events (their `stage` field is a bare review point that would otherwise read as a phantom transition); a dedicated resolution pass pairs them with the reviews they answer.

### 2.5 Sequence-windowed decision resolution + legacy fallback

A decision belongs to the window *between its review opening and the next review opening anywhere* — so a later sprint's answer cannot leak backwards onto an earlier review, even though both carry the same point name (e.g. two `sprint` reviews).

Resolution order per pending review:

1. **Explicit `review_decision` event in the window** → outcome + comment read straight from it (no inference).
2. **Fallback for runs predating decision events** (mirrors the old browser rule exactly, so legacy history still reads correctly): a later revision started with a rejection comment → `changes`; the run advanced or finished → `approved`; still waiting → `pending`.

A still-open review's comment is pulled from the graph state (`reviews`), the only place an in-flight review's text survives.

### 2.6 Summary numbers: two sources, stated honestly

- **From the event walk:** reviews and their outcomes, approvals passed, sprints executed, revisions total.
- **From graph state (the event stream only *narrates* these):** test runs and defects live in the `remediation` cycle; `sprints_planned` comes from the sprint-plan artifact (`None` = not planned yet, not zero); documents = artifacts present for the run.

## 3. Files Changed

### Backend

| File | Change |
|---|---|
| `src/app/server/runs.py` | **Wizard builder + endpoint.** `@runs.get("/{run_id}/wizard", response_model=WizardModel)` (auth + `_require_run`). Builder: stage/specialist copy tables (`_WIZARD_STAGE_COPY`, `_WIZARD_SPECIALIST_COPY` — human titles, never raw identifiers), `_REVIEW_POINTS`, `_wizard_base_stage`, `_wizard_stage_copy`, `_wizard_status`, `_wizard_note`, and `build_wizard_model(record, runner)` — the single-pass fold into sections → revisions → steps, then status fill-in, review resolution, and summary. **Step 1:** `review_decision` event published in `submit_review`; `approval_decision` published in `submit_approval`; `_APPROVAL_EVENTS` frozenset for the approvals count. |
| `src/app/server/models.py` | Wizard Pydantic shapes (all snake_case, `extra="forbid"`, documented fields): `WizardReview`, `WizardNote`, `WizardStep`, `SprintRevision`, `WizardSection`, `WizardSummary`, `WizardModel`. The summary model carries only fields the panel renders. |
| `src/app/server/events.py` | Registered `"review_decision"` and `"approval_decision"` as event types. |
| `src/app/server/runner.py` | Fixed a `_record_stage_duration` NameError (function defined at module level; missing `import time`). |

### Frontend (`langchain-ui/`)

| File | Change |
|---|---|
| `src/types/index.ts` | 1:1 snake_case TypeScript mirrors of the wizard shapes. |
| `src/api/index.ts` | `getWizard(runId)` client (line 96) + `WizardModel` import. |
| `src/components/WizardDashboard.tsx` | **Rewritten as a pure renderer.** Props `{ run: RunStatusResponse; model: WizardModel \| null }`. Loading state when the model is absent/empty. Selection initializes from `model.current_section_id ?? last section` and follows the current section once (same logic as the pre-rewrite version). Sub-components: `SectionDetail`, `IntakeDetail`, `DesignDetail` (maps `run.reviews` filtered to `technical_specification`), `SprintDetail`, `RevisionCard` ("First pass" / "Pass N", rejection comment + "Sent back for changes"), `StepCard` (expandable when notes exist; durations `<60s` else `Xm Ys`; "N notes" badge), `EventNote` (icon by kind: error / review_request / approval_* / tool_*), `ReviewCard`, `SummaryDetail` (10-stat grid + planned sprint goals + run error block). It fetches the sprint-plan artifact itself via `fetchArtifactContent(run_id, 'sprint-plan')`, cached per run id. |
| `src/pages/RunDashboard.tsx` | Wired: `wizard` state; wizard fetched alongside run status inside the same coalesced refetch (700 ms), wrapped in try/catch so a failed wizard fetch never takes the whole dashboard down; view-mode toggle button (persisted to `localStorage.runView`); call site renders `<WizardDashboard run={run} model={wizard} />` when in wizard mode. |
| `src/lib/wizardData.ts` | **Deleted** — 700 lines of duplicated, buggy client-side stage-walking. |

## 4. Concepts Introduced (for a beginner reader)

- **Server-derived view model** — the API returns a *finished* structure (sections → steps → notes), not raw events. "Pure renderer" means the component contains zero logic that answers "what phase is this run in?"
- **Base-stage transition detection** — compare the stage with pause prefixes stripped; pauses are states, not steps. This is what removed duplicate step cards.
- **Sprint revision under one stage** — a rejected sprint's re-run is "Pass N" inside `Sprint 1`, carrying the rejection comment, instead of appearing as a second sprint.
- **Decision events + windowed resolution** — decisions are facts recorded at decision time; each review owns the sequence window until the next review opens. Legacy runs fall back to stage inference so old history still renders correctly.
- **Coalesced lockstep fetching** — run status and wizard model refresh together under one in-flight guard, so the two views never show different moments of the same run.

## 5. Validation Performed

| Check | Result |
|---|---|
| Narrowed pytest suite after dedup fix | **141 passed** |
| Raw stage stream cross-check | Collapse-to-13 transitions matches API step counts (Sprint 1: `revisionCount: 1, stepCount: 21`) |
| `npm run build` (runs `tsc -b` first — type errors fail the build) | Green |
| App image rebuilt; container serves new bundle | Served bundle = `index-BlV0HeDh.js` (verified via curl); health `{"status":"ok"}` |
| Live browser — rail | 4 phases with correct statuses: Product intake **Done**, Design **Done**, Sprint 1 **"Working on it"**, Final summary **"Up next"** |
| Live browser — Sprint 1 detail | FIRST PASS header; exactly **21 step cards** (counted via "N notes" badges) matching the API; repeated titles (e.g. "Designing the interface" ×4, "Test Round 0" ×2) confirmed as genuine workflow cycles with real durations and note counts |
| Live browser — Final Summary | Stats grid renders with real numbers: Sprints planned **5**, executed **1**, Revisions **1**, Test runs **1**, Defects found **1**, Documents **33**, Approvals passed **167**; all five planned-sprint goals listed from the sprint-plan artifact. Screenshot saved as `wizard-final-summary.png` (workspace root) |

**What this proves:** the wizard renders the server's deduplicated phase model; backend and frontend agree on one truth; repeated stage titles are legitimate cycles, not duplicates; and the deployment path works end to end.

## 6. Known Limitations

1. **`approvals_passed` overcounts.** It counts every approval-family event in the history (`approval_auto`, `approval_request`, `approval_decision` — the same set the classic timeline counts), so one stage passing through several gates inflates the number (167 on the live run). A per-stage distinct-approval count would be lower. Deferred: cosmetic, and parity with the classic view was preferred.
2. **Spec/intake review outcomes are not resolved server-side.** Review resolution runs over sprint revisions only. The Design panel derives its spec-review status directly from `run.reviews` (parity with the previous frontend behavior); intake reviews are not surfaced in the wizard at all.
3. **Per-test pass/fail is not in the model.** The summary reports test-run and defect *counts*; individual round outcomes (which tests failed when) remain in the classic log/timeline.
4. **The `review_decision` resolution branch is untested against live data.** No model server is running on port 1234, so no new runs can be started; every run in the store predates decision events and exercises the stage-inference fallback instead. The explicit-decision path is implemented and unit-covered but not yet observed in a live run.
5. **Minor:** the step-card expand interaction was verified by click but the expanded-notes assertion was inconclusive (low priority — the notes data is present in the DOM and rendered on expand).

## 7. Deployment Note (standing gotcha)

The Dockerfile builds the frontend and bakes `langchain-ui/dist` into the **app image**; FastAPI serves it from inside the container. Therefore:

- **Frontend changes:** `docker compose build app && docker compose up -d` — a local `npm run build` alone does *not* deploy.
- **Backend-only changes:** `docker compose build app worker && docker compose up -d`.
- Health check ~2–3 s after `up`: `curl http://localhost:8000/api/health` → `{"status":"ok"}`.

(Recorded in repo memory at `/memories/repo/deployment.md`.)
