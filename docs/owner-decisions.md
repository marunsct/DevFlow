# Owner decisions register

The one place for decisions the owner has made that are still in force: what was decided, whether it is
applied, and, for a deferred one, what starts it. Agents read this before acting on any of these subjects.
Newest group first. When a deferred decision is applied, change its status here in the same commit.
Older owner decisions are in the archive (`docs/ARCHIVE.md`) and the agents' memory notes.
Anything still in force from them belongs here too.

Status words:
- **Applied**: done and live.
- **Deferred**: approved, with its trigger named.
- **Owner action**: only the owner can do it. The harness never changes the owner's models, machine or accounts.
- **Waiting**: blocked on something named.

## 2026-11-27 (owner: build the model diagnosis design's first three items)
Context: `reports/research/2026-11-27-model-diagnosis-design.md`. Approved: Phase 0 (DX.1-DX.5), DX.6 (speed and
concurrency profile), DX.7 (reasoning dose-response) with the minimal DX.8 replay set it needs, and, in the owner's
words, "if the model supports more parallel request run the diagnosis parallely".

| # | Decision | Status | Trigger / where it lives |
|---|---|---|---|
| 1 | Settings the diagnosis finds are applied behind one switch, `PROFILE_FROM_DIAGNOSIS`, with every field overridable on the settings page; a value the owner set always wins. | Built (LF.1602, LF.1603); live with the bundle's deploy. Compose default **on** (the owner's "switches ON, off on a drastic change": each field is measured by a rule that takes no value whose answers pass less often, and each is overridable) | `models/diagnosis_profile.py`; Settings -> Models -> "Measured settings". `MODEL_SESSION_SCOPE`, set by compose and `.env`, counts as the owner's and wins over the measured scope. |
| 2 | The full calibration tier starts only from the settings page, never by itself. | Built (LF.1603); live with the bundle's deploy | "Full calibration" on Settings -> Models (`POST /api/settings/model/steering/diagnose {"full": true}`); runs and `loop.sh diagnose` use the quick tier only. |
| 3 | Only benchmark runs' transcripts may become probes - never the owner's own runs, never hidden tests. | Built (LF.1603) | `scripts/loop/replay_set_build.py` reads only runs scored against their family's own brief (`data/bench`); `replay_set.leaks` refuses a run id, a host path or a hidden test's line, and the suite checks the shipped set. |
| 4 | The model under test is diagnosed again after the first step (Phase 0), before runs resume. | Waiting | The main session does it once Phase 0 is deployed. |
| 5 | The diagnosis runs its independent requests side by side, up to what the server really serves at once, never above it. | Built (LF.1601); live with the bundle's deploy | `models/diagnosis_pool.py`: the slots less live runs' calls in flight; a hosted model 2 at once and `DIAGNOSIS_MAX_COST_USD`. |

## 2026-11-18 (owner, about 16:25 JST: "implement all the improvement plans as per the recent review findings")
Context: [Harness Deep Review 2026-11-18](https://claude.ai/artifact/9nhWdxAtiiatDkDiLR5Wwx), its plan (Phases 0-3) and
its six decisions. Read as approving the plan and decisions 1, 2, 3 and 5; 4 and 6 spend money or are owner actions.

| # | Decision | Status | Trigger / where it lives |
|---|---|---|---|
| 1 | Pause the language sweep and the release-candidate count; work the review's Phases 1 and 2 instead. | Applied | Resumes when Phase 1 items 1.7 and 1.8 (language rows, golden examples) are built. |
| 2 | Frozen-version measuring: no deploys into a live run except for a bug that changes its outcome; fixes ship at run boundaries in bundles. Supersedes the 2026-11-05 "deploy each verified fix at once" rule. | Applied | `AGENTS.md` mid-run deploy rule narrowed to outcome-changing bugs. |
| 3 | Roles are removed or merged only after a measured ablation shows no score change, one at a time. Owner features (role injection, parallel/linear toggle, sprint summary, work orders, templates, Sprint Record) are not touched. | Applied | Review item 2.8. |
| 4 | One small hosted-model test (architect contract and stuck-defect escalation on a stronger model). | **Approved 2026-11-18 ~21:20 JST: Anthropic, Claude Haiku 5.5 (`claude-haiku-5-5`), $30 of credit.** Waiting on the owner to enter the key and the judgement model in Settings (admin only; the harness has no Anthropic key configured). Ceiling $8 per run (LF.1107). | Owner enters the key; then hybrid runs (judgement on Haiku, build local), then full-Haiku runs, until about $25 is spent. |
| 5 | "Launch" means a private, self-hosted, single-tenant beta for 5-10 invited users on a supported matrix (Python and JavaScript small services; other stacks experimental), with the time budget stated. | Applied | Review item 3.7 (supported matrix at intake). |
| 6 | Move the operator login out of tracked `docs/HANDOVER.md` and rotate it before any outside user. | **Owner action** for the rotation; the move is done with it. | Before the first outside user. |

## 2026-11-17 (owner, about 10:00 JST: build the rest in parallel, behind switches, measured on the runs already made)
"complete the partly done and pending items in parallel ... can we use past run as without measurement so that we dont
waste time on running it again, do the development behind switch do the measured runs if find any drastic changes we can
turn off the switch and measure to verify ... complete this product as efficiently and quickly as possible".
- Applied: the remaining launch-review items are built in parallel (one worktree each), new behaviour behind a switch;
  the scored runs already made are the baseline - no new "off" runs first.
- Applied: the 10 built-but-off switches are ON from 11-17 (`EXPERIMENTS_ON`), with NEAR_GREEN_REPLANNED_ONCE; each new
  switch goes on when deployed.
- The rule for "drastic": a run a switch fired in loses a hidden test, or takes 1.5x its family's 5-run active minutes
  (the KPI check already flags 1.5x). Then that switch, or its group when firing is not recorded, goes off and the next
  run of that family verifies. Caveat kept: switches on together are told apart by their firing signals (M10: most
  have none yet), so firing signals are added as each switch is touched.
- Waiting on the owner: LR.44 (hosted-model runs cost money; needs an explicit yes, provider and budget).

## 2026-11-10 (owner, about 21:30 JST: "go ahead with the recommendations")

Context: [backing-services plan](backing-services-plan.md) §7 and the
[owner summary doc](https://claude.ai/artifact/Fo6uKW8ZE1swhpHf6zrrjU).

| # | Decision | Status | Trigger / where it lives |
|---|---|---|---|
| 1 | **Launch first.** The backing-services broker phases (E, F, G) come after the release candidate; Phases A to D can be built alongside. | Applied: launch plan in `docs/STATE.md` | Launch order: Measure batch, Fix batch (LF.801 onward), learning runs, then the release candidate (three clean runs per family). |
| 2 | **Cancel the owner's paused run `run-038f45bb`** ("low brief", admin, paused 11:33 awaiting approval). | **Waiting.** The agent's cancel was refused by the session's permission check, because it is the owner's run. | The owner cancels it from the run page, or allows the agent to. Until then the loop leaves it alone. |
| 3 | **Use a higher-bit build of Qwen3.6-35B-A3B on :1234.** Today it is IQ4_XS (4-bit), and the readiness check advises a higher-bit build. Match :8888's build so the two ports compare. | **Owner action. 2026-11-11 22:48 JST: the owner loaded `qwen3.6-35b-a3b-mtp@iq4_nl` on :1234** (IQ4_NL, the owner's choice to match :8888); the readiness check reports it as 4-bit and still advises a higher-bit build. | The harness maps a run pinned to the old name onto the new build. A higher-bit build stays open if the owner wants it. |
| 4 | **Product command execution stays opt-in** on a fresh install (`ALLOW_COMMAND_EXECUTION=false` by default). | Applied: documented in `docs/PRODUCT.md` §11 "First-time setup" | None. A10 is closed with no code change. |
| 5 | **`net-floor` sidecar with NET_ADMIN.** A one-shot container in the worker's network namespace that applies egress rules by user id. Product code can then reach neither the harness's services nor :8888/:1234. The worker gains no capability. | Deferred, approved | Built as plan item A8, after the A8 spike and after A7 (a user id per run). |
| 6 | **E1 spike:** throwaway service containers, including Keycloak, and the worker joining a test network between runs. | Deferred, approved | First step of Phase E. Run between runs only, never during a Measure batch. |
| 7 | **Docker socket mounted into a socket proxy, with a harness broker starting service containers through it.** A broker bug could affect any container on Docker Desktop, and the plan says so. | Deferred, approved **only after #5 and A7 are live** | Phase E. Product code, agents and graders never get a socket. |
| 8 | **Docker Desktop VM memory from 3.8 GiB to 8 GiB.** At 3.8 GiB only small services fit; Keycloak, Kafka, RabbitMQ, OpenSearch, MongoDB and MySQL stay at "your own instance or an adapter". | **Applied by the owner 2026-11-11 10:04 JST: 16 GiB** (`docker info` reads 15.9 GiB, 8 CPUs), more than the 8 GiB asked. | Phase E's medium services (Keycloak, Kafka, RabbitMQ, OpenSearch, MongoDB, MySQL) now fit; still built only after the release candidate (#1). |
| 9 | **Image pulls:** a 15 GB quota and a nightly pre-pull of pinned service images. | Deferred, approved. **Waiting** on the owner naming which Docker Hub login the pre-pull uses. The loop's operator account is not a Docker Hub account. | Phase B0 served mode, D, E. Until the owner names a login, pulls are anonymous and rate-limited. |
| 10 | **Licence-class opt-ins** (SSPL, BUSL, RSAL, Redpanda BSL: MongoDB, Redpanda, Redis 7.4 to 7.8 and the like). | Decided: **off** | Switched on only from the owner's settings page, and only when a product brief needs one. Until then such a service resolves to the owner's own instance or an adapter, plus a release gap. |
| 11 | **Real scoped cloud credentials** (Amazon S3, Azure, GCS, Atlas, an identity provider) for testing products against external services. | Decided: **not now** | The owner adds them through Connections (Phase C) when wanted. Any cloud cost is the owner's. |
| 12 | **`files-api` and `jobs-api` become Measure families**, not gate families yet. | Deferred, approved | Phase B0. Register them in `docs/measuring.md`; gate membership is decided later. |
| 13 | **The harness's own Redis image:** keep `redis:7-alpine` (password-protected since LF.790) until after launch, then move to Valkey (BSD, drop-in). | Deferred, approved | After the release candidate, at a run boundary: flush the queue, change the image and the healthcheck, then run the readiness check. |

**Also decided by the agent and accepted by the owner:**
- The service catalogue lives in `src/app/stacks/services/` as data (a "service pack"). Model-facing wording stays in `src/app/plugins/seed.py`, per AGENTS.md.
- No fix is deployed into a running Measure batch; fixes found are built, committed and held for the Fix batch.

## Earlier decisions still shaping the loop (pointers)

- **Measure/Fix:** a Measure batch runs on one frozen harness, two runs per family, scored by hidden tests only; bugs found are filed for the Fix batch (owner 2026-10-21; AGENTS.md).
- **The model is the owner's.** Run `loop.sh ready` before every run, and never load or change a model. Default settings may be changed to keep testing (owner 2026-11-09).
- **Switch policy:** bug fixes and quality changes are always on, with no switch. Only optional, non-quality improvements go behind switches, and they are measured (owner 2026-11-05).
- **Docker Desktop:** the agent may restart Docker Desktop when deploys hang, after pausing runs (owner 2026-11-09).
- **Never commit the owner's uncommitted `docker-compose.yml` edit** (the `127.0.0.1:5433:5432` db port). A pre-commit guard enforces this (LF.789; run `scripts/loop/install_hooks.sh` once per clone).

## 2026-11-23/24 (scale review)

- **Web tools on for every run** and measured from there; the medium and high briefs are not counted in the measuring (owner 2026-11-23, LF.1234).
- **Deep review of medium-brief failures approved to build** (owner 2026-11-24): `reports/audits/2026-11-24-why-medium-briefs-fail.md`, bundles 1-3.
- **Per-sprint locking of the acceptance suite: build it** (owner 2026-11-24 10:1x JST). The criteria and the interface contract are fixed up
  front; each sprint's tests are written and locked by QA at that sprint's start, against the running product of the earlier sprints; a sprint's
  gate runs only due tests (its own and the earlier, locked ones); the whole suite runs at release. A one-sprint product is unchanged.
- **Rerun the medium brief once bundles 1 and 2 are deployed** (owner 2026-11-24): the same brief (`brief_medium.md`), as the proof of the scale work.
- **Model split** (owner 2026-11-26, replaces 11-24): Sonnet for routine run audits and chat; Opus for code builds; Fable for research, review and planning.
