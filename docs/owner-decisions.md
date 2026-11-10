# Owner decisions register

The one place for decisions the owner has made that are still in force: what was decided, whether it is
applied, and, for a deferred one, what starts it. Agents read this before acting on any of these subjects.
Newest group first. When a deferred decision is applied, change its status here in the same commit.
Older owner decisions are in `docs/HANDOVER.md`, `docs/improvement-plan.md` and the agents' memory notes.
Anything still in force from them belongs here too.

Status words:
- **Applied**: done and live.
- **Deferred**: approved, with its trigger named.
- **Owner action**: only the owner can do it. The harness never changes the owner's models, machine or accounts.
- **Waiting**: blocked on something named.

## 2026-11-10 (owner, about 21:30 JST: "go ahead with the recommendations")

Context: [backing-services plan](backing-services-plan.md) §7 and the
[owner summary doc](https://claude.ai/artifact/Fo6uKW8ZE1swhpHf6zrrjU).

| # | Decision | Status | Trigger / where it lives |
|---|---|---|---|
| 1 | **Launch first.** The backing-services broker phases (E, F, G) come after the release candidate; Phases A to D can be built alongside. | Applied: launch plan in `docs/STATE.md` | Launch order: Measure batch, Fix batch (LF.801 onward), learning runs, then the release candidate (three clean runs per family). |
| 2 | **Cancel the owner's paused run `run-038f45bb`** ("low brief", admin, paused 11:33 awaiting approval). | **Waiting.** The agent's cancel was refused by the session's permission check, because it is the owner's run. | The owner cancels it from the run page, or allows the agent to. Until then the loop leaves it alone. |
| 3 | **Use a higher-bit build of Qwen3.6-35B-A3B on :1234.** Today it is IQ4_XS (4-bit), and the readiness check advises a higher-bit build. Match :8888's build so the two ports compare. | **Owner action.** Agents never load or change a model. | When the owner loads it, the readiness check reports the new build. Until then, compare ports knowing :1234 is 4-bit. |
| 4 | **Product command execution stays opt-in** on a fresh install (`ALLOW_COMMAND_EXECUTION=false` by default). | Applied: documented in `docs/PRODUCT.md` §11 "First-time setup" | None. A10 is closed with no code change. |
| 5 | **`net-floor` sidecar with NET_ADMIN.** A one-shot container in the worker's network namespace that applies egress rules by user id. Product code can then reach neither the harness's services nor :8888/:1234. The worker gains no capability. | Deferred, approved | Built as plan item A8, after the A8 spike and after A7 (a user id per run). |
| 6 | **E1 spike:** throwaway service containers, including Keycloak, and the worker joining a test network between runs. | Deferred, approved | First step of Phase E. Run between runs only, never during a Measure batch. |
| 7 | **Docker socket mounted into a socket proxy, with a harness broker starting service containers through it.** A broker bug could affect any container on Docker Desktop, and the plan says so. | Deferred, approved **only after #5 and A7 are live** | Phase E. Product code, agents and graders never get a socket. |
| 8 | **Docker Desktop VM memory from 3.8 GiB to 8 GiB.** At 3.8 GiB only small services fit; Keycloak, Kafka, RabbitMQ, OpenSearch, MongoDB and MySQL stay at "your own instance or an adapter". | Deferred, approved. **Owner action:** the harness never changes the VM. | Before Phase E's medium services. The owner sets it in Docker Desktop settings, at a moment with no runs live. |
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
