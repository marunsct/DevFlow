# Backing services, lifecycle services and object storage: final implementation plan

*2026-11-10 (JST). Status: PLAN (final). This document changes no code. It replaces Phases B-G of the first plan and absorbs `docs/object-storage-plan.md` OS.0-OS.8. OS.9 and OS.10 do not exist in any repo document; they are defined here.*

*Already done and committed:*
- *LF.782: seeding glob (A1, `47190e23`)*
- *LF.783: install refuses harness hosts (A5, `a9f858ce`)*
- *LF.784: network line by mode, and the PORT/DATA_DIR line in every stage (A4, `c5d22b1d`)*
- *LF.785: stale browser line removed; the database role defers to the stack (A6, `c5d22b1d`)*
- *LF.786: a fresh install keeps files locally; a key with an empty secret is refused (A2 core, `98eb0981`)*

*The next Appendix M row is **LF.788** (LF.787, the outside-writes cap, was taken by the loop).*

*Marks:*
- ***(u)*** *means unverified or an estimate. It is measured on this host before it gates anything.*
- ***(verified)*** *means checked read-only on the live host on 2026-11-10.*
- *Compose line numbers are from the working copy, which holds the owner's uncommitted `127.0.0.1:5433:5432` hunk at `:188-189`. On a clean checkout, subtract 2 from every compose line after 185.*

---

## 1. Decision summary

1. **Every product boots with no services.**
   - It starts from `PORT` and `DATA_DIR` alone, with a working fallback shape for each category it uses. This is tier 0 and is always on.
   - An "alone" start check enforces it on every run, even when services are provided.
   - An empty-plan run gets no service variables and an unchanged environment contract text. The run is not byte-identical overall, because:
     - B3 adds a schema field;
     - B8 adds an alone start;
     - A7, A8 and A12 change timings.
   - The sentinels are therefore re-baselined after A7 and after B (§6).
2. **A deterministic resolver is the core.** Plain code, not the model, maps each service the brief names (with a quote) to a catalogue entry, and takes the first tier that applies.

   | Tier | Meaning |
   |---|---|
   | A | Bring your own (BYO) or an external service |
   | B | A real container, pinned by digest |
   | C | An official emulator |
   | D | A same-protocol substitute |
   | E | An adapter, contract tests and a recorded release gap |

   - **The design fails visibly, not closed.** Every step down a tier writes its reason to the specification, the environment contract and the Sprint Record. Only `required_real` refuses a run.
   - The model never chooses an image.
3. **Service knowledge is data.**
   - The tracked catalogue lives in `src/app/stacks/services/`, as a "service pack" shipped in the image.
   - Engine code lives in `src/app/services/` and names no service. A test enforces this.
   - Model-facing wording stays in `seed.py` rows keyed by entry id.
   - The category fallback wording rendered from `_categories.toml` is also model-facing. It needs the owner's ruling (open question 1) before B1.
4. **BYO and external services come first, because they need no Docker.** This covers:
   - Amazon S3 and self-hosted S3-compatible stores;
   - Azure Blob and GCS;
   - Atlas and HANA Cloud;
   - Auth0, Okta and Entra;
   - any custom service.

   How it works:
   - They are Connections in settings, with encrypted secrets, a connection test and a per-run namespace.
   - The product sees the same variables as in every other tier.
   - A run that carries a real credential is forced onto the egress allowlist (A12).
   - The harness's own artifact store makes the same choice explicitly: local, self-hosted S3-compatible, or Amazon S3.
5. **Real containers are started only by a harness-owned service broker.**
   - The broker reaches Docker only through a socket proxy, which is the only container holding the socket.
   - Each run gets:
     - `--internal` networks;
     - hard memory, CPU and pids limits;
     - `OomScoreAdj=500`;
     - an aggregate CPU cap and a free-disk floor.
   - There are never published ports (except the scoring network on 127.0.0.1), `--gpus`, devices or bind mounts.
   - Every create body is built from typed fields, validated before create and re-checked with inspect afterwards.
   - The proxy filters API paths, not request bodies. With `CONTAINERS` and `POST`, it also allows update, kill and archive on any container on the engine. E1 evaluates a method-and-path proxy. Either way, a broker bug can affect every container on the Desktop engine, and this plan says so plainly.
   - Product code, agents and graders never get a socket.
6. **Uncatalogued open-source services are learned between runs.**
   - `loop.sh services learn` runs nightly from the request queue, and on demand.
   - It accepts only:
     - Docker Official or Verified Publisher images, or an owner-trusted namespace;
     - an OSI licence per version, confirmed by two sources.
   - It pins by digest, learns the run contract from the image config and cited docs, smoke-tests inside the broker, and writes a learned entry for the owner to review.
   - It runs one smoke test at a time host-wide, only when the memory gate admits it, and never during a Measure batch.
   - Learning at intake time is deferred (Phase I).
   - Hand-curated entries follow the same trust rule.
7. **Licensed services never start without the owner's recorded acceptance.**
   - Source-available-free-dev licences (SSPL, RSAL, BUSL and the like; this covers MongoDB and Redpanda) take one opt-in per licence class. This is built now.
   - Vendor dev licences (HANA, Oracle, SQL Server, Db2, Neo4j EE, Couchbase EE) resolve to tier A or E until the VM has 12 GiB or more. Their tier-B plumbing is filed (Phase I).
   - Closed SaaS goes to tier A or E.
8. **The owner's machine comes first.** Services live inside the Docker Desktop VM (3.82 GiB, verified). The GPU models run on the host, outside it.
   - **Memory gate:** it reads the VM's MemAvailable.
   - **Aggregate CPU cap:** 2 CPUs host-wide to start.
   - **Free-disk floor** before any pull.
   - **Per-run uid (A7):** product processes run under their own uid, from a pool, so they cannot read worker secrets.
   - **Egress floor (A8):** a one-shot sidecar applies it in the worker's network namespace. It keeps product code away from harness services and from the owner's :8888 and :1234.
   - **Model tokens/s:** read passively from harness telemetry.
   - **VM size:** the harness never changes it. The owner's decision to keep or raise it gates Phase E.
   - **At 4 GiB only class S fits.** These stay at tier A (a Connection), D or E until the VM grows:
     - Keycloak (unless the E1 capped-heap measurement makes it class M);
     - Kafka and RabbitMQ;
     - OpenSearch, Elasticsearch and Solr;
     - Airflow;
     - MongoDB, MySQL and MariaDB;
     - the Pub/Sub and Service Bus emulators;
     - HANA, Oracle, SQL Server and Db2.
9. **The product's lifecycle files are validated statically, with no network.** At tiers 0-1:
   - the core seven validators;
   - a pinned Kubernetes CRD schema catalogue;
   - OpenTofu, tflint and ansible-lint.

   Real execution (tiers 2-3) and building the product image are filed. They never run in the owner's Desktop VM without a separate engine.
10. **Two new families measure the work.**
    - `files-api` runs in alone and served modes.
    - `jobs-api` runs in served mode, plus artifact checks.

    Served mode gives the broker a scored path under MF.4. The existing families keep empty plans.

**Why this approach (§8 separates verified sources from unverified ones)**

| Alternative | Who does it | Verdict here |
|---|---|---|
| No services; substitutes only | SWE-agent. Jules' setup does not support long-running processes, but its base image ships Docker 28.2.2 and Compose v2.36.2, it offers hosted services through MCP partners (Neon, Supabase), and it goes read-only on 2026-11-11 and closes on 2026-12-31, so it is weak evidence | Kept only as tier 0/E. On its own it fails the owner's goal |
| The agent runs docker/compose itself | OpenHands (the agent runs `docker compose up` in a privileged canvas) | Rejected. Product commands run on the owner's single Docker Desktop VM, so a socket in agent hands is root on a VM that shares the owner's files |
| Configured setup steps start services inside the agent's VM | Devin (blueprint apt and systemd steps, proposed by the agent and validated); Cursor (a configured `start` step, `sudo service docker start`) | Not adopted, for the same reason: here the "VM" is the owner's shared Desktop VM |
| Declared service containers per job, with health commands | Copilot `copilot-setup-steps.yml` `services:` with `--health-cmd`. Since 2026-10-28, Copilot's default cloud sandbox supports no setup steps and no services | Adopted as the shape of the specification only. Copilot's setup fails open. This plan fails visibly: every step-down is recorded, and `required_real` fails closed |
| The agent never gets the host socket | OpenHands `DockerWorkspace` and Enterprise (127.0.0.1 binding, env allowlist, resource limits; Enterprise also uses Sysbox and never mounts the host socket for the harness) | Partly borrowed: no socket in agent hands, 127.0.0.1 binding, env allowlist, limits. Not borrowed: this plan does mount the host socket, into a proxy, which Enterprise avoids |
| Egress allowlist, with declared external hosts added | Codex (saving a network secret adds its hosts), Devin's security floor. Copilot's firewall covers only Bash, which shows that partial enforcement leaks | An allowlist only for runs that carry a real Connection credential (A12). Other runs get a denylist floor (A8), which is weaker than Codex. Enforcement is by uid, not by tool |
| Processes do not survive a snapshot | Cursor, the Codex start skill, OpenHands `setup.sh` | Adopted: services are ensured again on resume and rewind |

**What no leader does that this plan adds:**
- provisioning from a brief through a catalogue;
- a licence gate;
- co-tenancy with GPU model servers;
- one declaration that moves a service between local and external;
- static validation of the product's CI, Kubernetes, Helm and IaC files in isolation, with no network, on a shared host.

Leaders validate these files in other ways:
- OpenHands Enterprise builds Dockerfiles and runs compose.
- Copilot relies on real Actions CI.
- Devin checks CI status and validates its own blueprints.

**Reconciling with the first plan's "no broker now":**
- The owner's explicit request makes automatic provisioning a requirement, which supersedes K.2 (embedded first). The socket mount itself still needs a specific yes (§4, §7).
- MF.4 parking is answered by the served-mode families. If the owner rules that served mode does not count, a fallback MF.4 exception is requested (§6).
- Effort and risk are staged:
  - the resolver core, BYO, the validators and object storage deliver value with no socket;
  - the broker comes only after A7, A8 and the owner's yes.

**Dropped from the drafts:**
- a shared `services` pool with a database index per run (that is namespacing, not isolation);
- OS.9, a shared SeaweedFS identity for products, whose scoping is unverified;
- the in-worker process runner (E0), which has no per-service memory limit inside a worker whose limit is larger than the VM (filed);
- intake-time learning (deferred to Phase I).

---

## 2. What happens today

**Product commands**
- **Execution mode.**
  - The live host runs `in-container`: `.env` sets it, and `printenv` shows it (verified).
  - The compose default is `container` (`docker-compose.yml:106`), and `.env.example:176` also says `container`. That mode needs a socket, and the socket is `/dev/null`. A fresh install may not run product commands at all (A10).
- **In-container mode** runs product commands as children of the Celery worker (`src/app/tools/sandbox.py:856-876`; `_execute_here` at `:4918`, which calls `_child_environment` at `:4978`).
  - They run as uid 10001 (`Dockerfile:126`, image `USER appuser` at `:223`), the same uid as Celery.
  - `preexec_fn` applies only rlimits and `os.setsid()` (`_apply_limits` at `:1174`, `:1342`).
  - There are two worker slots (`--concurrency=${CELERY_CONCURRENCY:-2}` at `docker-compose.yml:318`, `--max-tasks-per-child=50` at `:319`).
- **The child environment is an allowlist only on the main path:** `_ENV_PASSTHROUGH` at `:959-963` (it passes `HTTP(S)_PROXY`/`NO_PROXY`) and `_child_environment` at `:1109`. Two paths run product or model-written code with the **whole worker environment** (DB_URL, JWT_SECRET_KEY, provider keys):
  - `src/app/acceptance/start_probe.py:76-79` starts `start.sh` with `{**os.environ, ...}`. `START_PROBE` is built in and always on (`src/app/switches.py:96`).
  - `src/app/acceptance/spec_dry_run.py:92` runs model-written spec files in node with no `env=`. `SPEC_DRY_RUN` is on (`docker-compose.yml:67`).
  - `start_output.py:116-123` uses `SandboxExecutor` and is fine.
- **Secrets are readable through `/proc` (verified).** uid 10001 can read `/proc/<pid>/environ` of PID 1 (docker-init; `init: true` at `docker-compose.yml:291`) and of every Celery process. Only readability was checked; no values were printed.
- **The worker has no tools for A7 or A8 yet.**
  - Its bounding set (`CapBnd a80425fb`) includes SETUID, SETGID, SETPCAP and KILL, and NoNewPrivs is 0.
  - `setpriv` is present; `iptables`, `ip6tables` and `setcap` are absent.
  - Chromium sits under `/home/appuser/.cache/ms-playwright` (`Dockerfile:205-209`). `_child_environment` points every command there (`sandbox.py:1146-1150`), and `/home/appuser` is mode 0700 (verified).
  - The Celery umask is 0022 (verified).
- **The harness relies on uid 10001 to manage product processes.** It reads and signals them:
  - `acceptance/stray_services.py:38,47` finds orphaned services through the `HARNESS_SERVICE_OF` mark in their environ, then SIGKILLs them;
  - `sandbox.py:1288` and `start_probe.py:100` use `killpg`.
- **The network is shared with the worker.**
  - `NETWORK_CATEGORIES={"install"}` (`sandbox.py:853`) gates `install_egress.refusal` in in-container mode (`:5160`, LF.783) and is also used by `container` mode (`:5321-5360`).
  - Product code reaches `db`, `redis`, `app`, `searxng`, the internet and `host.docker.internal` (`docker-compose.yml:241,300`). The owner's models listen there, on :8888 and :1234 (no key).
  - Installs refuse harness hosts (`tools/install_egress.py:45-46` `HARNESS_HOSTS`), but reach at run time is not enforced.
- **There is no container runtime.**
  - The socket is `${DOCKER_SOCKET:-/dev/null}` (`docker-compose.yml:307`; verified as a character device 1,3).
  - No role has `docker`, and agents may not start servers (`sandbox.py:2345-2352`).

**Harness services and resources**
- **The harness Redis has no password and floats on a tag.**
  - `REDIS_URL=redis://redis:6379/0` (`:24`); no `--requirepass` (command at `:215`, `redis-cli ping` healthcheck at `:219`).
  - The image `redis:7-alpine` (`:213`) floats to 7.4.x, which is RSAL/SSPL and falls inside this plan's own licence watch range.
  - Consumers: `src/app/server/tasks.py:41,43`, `redis_client.py:29` (used by readiness) and `tests/conftest.py:254`.
- **The worker's limit exceeds the VM:** `memory: 8g` (`:341`).
- **VM (verified):** MemTotal 4,101,074,944 B (3.82 GiB), 8 vCPU, about 1.8 GiB available, 21 running containers (most without limits), Docker server 29.8.0 on x86_64.
- **Host (verified):** 91 GB RAM, 43-48 GB available, swap full. The AMD GPU is shared with the owner's llama-servers (RSS about 10.3 and 9.4 GB).
- **Deploys bring up only `app worker`.** Both `loop.sh deploy` and ship-live use `compose_up.sh app worker`.
- **The ship-live login lookup is fragile.** `ship_live.sh:19` reads the operator login with `eval "$(sed -n 65p docs/HANDOVER.md)"`, so any line inserted above line 65 breaks it.
- **A compose comment names a run id**, against AGENTS.md.

**Prompts and stack selection**
- After LF.784, the network line follows the execution mode (`src/app/agents/environment_contract.py`, `_describe_the_network` at `:29`). The "no way to start one" text is at `:138` and `:224`.
- Only PostgreSQL has a worked substitution rule (`seed.py:50-59`).
- Brief-named services land in free-text `TechnologyStack.additional_tools` (`agents/tools_models.py:57`) or in `database` (`:55`).
- The keyword extractor is told "Do not include tools" (`plugins/middleware.py:404-405`; `_extract_stack_keywords` at `:364`). The postgres row fires; service names the model treats as tools are dropped.

**Object storage**
- After LF.786, a fresh `.env` names no bucket, and a key with an empty secret is refused.
- **Still open:**
  - `MINIO_ROOT_*` (`docker-compose.yml:143-144`; `.env.example:127-128`);
  - `MINIO_API_PORT` and `MINIO_CONSOLE_PORT` (`.env.example:146-147`);
  - commented MinIO lines (`docker-compose.yml:238,297,348`);
  - "MinIO in compose" (`pyproject.toml:49`).
- **Wrong install message.** `object_store.py:163-164` says "Install the 's3' extra", but no such extra exists: `boto3>=1.35.0` is a core dependency (`pyproject.toml:53`).
- **Defect: `OBJECT_STORE_REGION` never reaches the code.** Compose `x-app-env` (`:141-146`) passes only BUCKET, ENDPOINT, ACCESS_KEY, SECRET_KEY and SECURE, with no `env_file`. The region advice at `.env.example:117-124` is lost, and the code falls back to `us-east-1` (`object_store.py:171`).
- **Amazon S3 problems:**
  - forced path addressing (`:177`);
  - `create_bucket` without `LocationConstraint` (`:200`; `head_bucket` at `:192`);
  - an empty endpoint silently means AWS (`:296`).
- **Only one ending archives.** Archiving happens only at `runner.py:1691` (complete or failed). These endings never archive:
  - the exception path (`:1561-1575`);
  - an identical-gate failure (`:1826`);
  - stalled (`:1915`);
  - `MAX_GATES` exhaustion (`:1944`);
  - cancelled (`:2083`).
- **Resumable endings.** `cancelled` and `failed` are in `RESUMABLE_STATUSES` (`:245`). `_finish_cancelled` hands off to `_finish_paused` on a pause (`:2084-2086`), and `BUDGET_PAUSE_STATUS` is at `:1572` and `:1714`.
- **Downloads read only the workspace.**
  - `download_artifact` (`runs.py:853`) and `_collect_artifacts` (`:1326`) read only the workspace, which `manage.py workspaces --delete` prunes (`manage.py:833`, `:1231-1240`).
  - `ensure_local` already exists (`object_store.py:344`; imported at `runs.py:85`). `list_prefix` exists in both backends (`:124`, `:255`) with no cap.
  - `archive_directory` is at `:370`.
- **Readiness turns any `"error"` into a 503.** `/api/health/ready` (`server/api.py:186-188`) returns 503 when any key other than `status` or `runs` reads `"error"` (`:250-254`).

**Lifecycle files, scoring and catalogue data**
- **Nothing is validated.** The harness writes `.github/workflows/<project>.yml` (`src/app/stacks/release.py:37,45`) and validates nothing.
- **Scoring inherits the host environment.** `scripts/bench/score.py` copies only `bench/"hidden"` (`:268`).
  - Its Playwright branch (`:283`) and pytest branch (`:299-308`) both run through `_run`, which merges the host `os.environ` (`:51-52`).
  - The pytest branch starts the product through `hidden/conftest.py:29` with `{**os.environ, PORT, DATA_DIR}`.
  - So scored products inherit the operator's host environment.
- **Families have no registry.** A family is a `benchmarks/<name>/` directory, and `loop.sh bench` reads `bench.json` (`kind`, `runner`, `tests`, `held_out_since`, `base`; `loop.sh:171-188`).
- **Switch registration has four parts:**
  - `src/app/observability/provenance.py:22 SWITCHES`;
  - `src/app/switches.py` `GROUPS` (`:144`), `BUNDLES` or `BUILT_IN`;
  - a compose `x-app-env` line;
  - a `docs/measuring.md` row.

  `switch_catalogue.py` only reads them.
- **Catalogue data has no home yet.** There is no `src/app/services/` package. `data/` is gitignored (`.gitignore:17`) and not in the image; the image copies `src/`, so TOML and JSON under `src/app/stacks/services/` ship. Stdlib `tomllib` is already used (`analysis/dependency_drift.py:273`).

---

## 3. Architecture

### 3.1 Flow

```
brief ─► stack selection: backing_services [{name, role, quote}] + deterministic alias scan (brief, database, additional_tools)
      ─► resolver (plain code): catalogue id │ category default │ unknown → catalogue request
      ─► tiers A→E per service (connections, licence records, trust, gate, arch, pre-pulled digests, required_real)
      ─► service plan (DATA_DIR/services/runs/<run>.json, never in the workspace) + ledger (.jsonl)
      ─► contract paragraph + specification "Backing services" section + seed rows for planned ids
      ─► provisioning in the background from intake:
           A: connection test + per-run namespace (+ proxied uid, A12)   B/C/D: broker ensure(run) → ready   E: nothing runs
      ─► first product command waits for ready (budget) → plan env for build/test/start
      ─► acceptance: served pass (plan env) + ALONE start check (no service env), always; two-instance check when a shared-state service is planned
      ─► _on_terminal: every ending archives; release and namespace deletion only on non-resumable endings (resumable ones keep leases until a TTL)
      ─► between runs: loop.sh services learn (request queue) → learned entries for owner review
```

### 3.2 Tiers

| Tier | When | Product sees | Scored as |
|---|---|---|---|
| **0** (always) | Every product, and every category it uses | When the setting is unset: the fallback shape under `DATA_DIR` | The alone mode |
| **A BYO** | The owner configured a Connection for the id (or a custom name), as the default or for this run | The same env vars via `byo.maps_to`, plus the per-run `byo.isolation`; the run uses a proxied uid (A12) | `non_comparable`. A `hermetic` connection is scored only by the in-worker acceptance suite until containerised scoring (Phase I); host-side `score.py` never receives it |
| **B real** | The entry has `[real]`; the licence is OSI or accepted; the trust record holds; the arch matches; the gate admits it; the digest is pre-pulled; the broker is present | Env with a run-scoped alias | Comparable. Tier and digest are fixed per Measure family |
| **C emulator** | No local real engine exists and a vendor emulator does (DynamoDB Local, Firestore, Pub/Sub, Azurite) | Env with dummy cloud credentials only | `emulated`, with gaps listed |
| **D substitute** | `auto=true` only where no B or C exists (fakesnow, BigQuery emulator, fake-gcs-server). Otherwise behind the group switch `SERVICES_SUBSTITUTES`, with per-entry `[substitute] enabled` data (FerretDB, Valkey-for-Redis, OpenSearch-for-Elasticsearch, OpenBao-for-Vault, Dex/Hydra/mock-oauth2-for-Keycloak) | Env | `substituted` |
| **E adapter** | Nothing above applies | No service. The product codes against an interface with a real adapter plus the in-process fallback, and contract tests skip with a reason when the vars are unset | Release gap: "not verified against <service>" |

**Rules**
- A service with no brief quote is dropped.
- An unknown name resolves to A (if a custom Connection exists) or to E, and files a catalogue request in `DATA_DIR/services/requests.jsonl`. The between-runs learner reads that file.
- `required_real` (an owner setting per service) refuses the run when neither A nor B is available. It is the only fail-closed path.
- Every step down records its reason, for example:
  - `gate: VM available 1.2 GiB < plan 1.5 GiB`;
  - `licence not accepted`;
  - `broker absent`;
  - `not pre-pulled`;
  - `trust record missing`.

### 3.3 The catalogue is data

**Location**
- `src/app/stacks/services/` is tracked and shipped. It holds:
  - `_categories.toml`: category, setting names and fallback shape;
  - `entries/<id>.toml`;
  - `_validators.toml` (including the dependency rows);
  - `_trusted_namespaces.toml`;
  - `licences/spdx.json` (pinned, with `isOsiApproved`);
  - `_licence_watch.toml`.
- Learned entries go to `/app/data/services/learned/` on the appdata volume. They are never committed automatically; the owner promotes one by committing it.
- Loading uses stdlib `tomllib`.

**Categories and product-facing settings** (data; the names are conventions):

| Category | Settings | Tier-0 fallback shape |
|---|---|---|
| sql | `DATABASE_URL` | Embedded file DB under `DATA_DIR` |
| document / wide-column / graph | Entry vars (`MONGODB_URI`, `CASSANDRA_CONTACT_POINTS`, `NEO4J_URI`) | Embedded store or files under `DATA_DIR` |
| cache / key-value | `REDIS_URL`, `MEMCACHED_SERVERS` | In-process map with expiry |
| queue / jobs | `QUEUE_URL`, or protocol vars (`REDIS_URL`, `AMQP_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `NATS_URL`, `MQTT_URL`) | In-process queue; jobs persisted under `DATA_DIR` |
| workflow engine | Entry vars (`TEMPORAL_ADDRESS`, `PREFECT_API_URL`) | Adapter plus in-process runner |
| object storage, S3 | `AWS_ENDPOINT_URL_S3` (unset means AWS), `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_PREFIX`, `S3_FORCE_PATH_STYLE` | Files under `DATA_DIR/objects`, keys preserved |
| object storage, Azure Blob | `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_CONTAINER` | Same as S3 |
| object storage, GCS | `GCS_BUCKET`, `STORAGE_EMULATOR_HOST` (emulator only), `GOOGLE_CLOUD_PROJECT` | Same as S3 |
| identity (OIDC) | `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUDIENCE` | Product-local dev issuer (key under `DATA_DIR`, discovery plus JWKS) |
| identity (SAML) | `SAML_IDP_METADATA_URL`, `SAML_SP_ENTITY_ID` | Adapter plus tier-E gap |
| directory (LDAP) | `LDAP_URL`, `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, `LDAP_BASE_DN` | Directory file under `DATA_DIR` |
| mail | `SMTP_URL` | `.eml` files under `DATA_DIR/outbox` |
| search | `SEARCH_URL` plus the entry's key var | Embedded full-text index |
| secrets / config | Entry vars (`VAULT_ADDR`-style) | Files under `DATA_DIR` |
| observability | `OTEL_EXPORTER_OTLP_ENDPOINT` | No-op exporter; `/metrics` still served |

**Entry schema.** Only the fields a built consumer reads ship. Later fields are added when an entry first needs them.

| Group | Fields | Added in |
|---|---|---|
| Identity | `id` (`^[a-z0-9-]{1,40}$`), `aliases`, `category`, `status` (approved / learned / review-needed / blocked), `provenance` | B1 |
| `[licence]` | `spdx`, `class` (permissive, copyleft, source-available-free-dev, vendor-free-dev, vendor-dev-licence, saas-only), `acceptance` (`none`, `class_opt_in`, `entry_opt_in`), `acceptance_env`, `terms_url` | B1 |
| `[env]` | `vars`, templated from `${host}` (run alias), `${password}`, `${db}` | B1 |
| `[byo]` | Non-secret fields, secret fields, `maps_to`, `isolation` (database / schema / keyspace / prefix / bucket_prefix / none), `connection_test` | B1 |
| `[substitute]` | Entry ref, `auto`, `enabled`, `abstraction_only`, `gaps` | B1 |
| `[trust]` | `tier` (T1, T2, or `namespace` with an owner record id) | B1 |
| `[real]` | `image`, `tag` (never floating, even with a digest), `digest` (required before enable), `arch`, `args` (typed list), `ports`, `engine_caps` (JVM heap, `MSSQL_MEMORY_LIMIT_MB`, `--maxmemory`), `cap_add` (a subset of CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER), `class` (S/M/H/X), `tmpfs_size_mb` | E2 |
| `[resources]` | `mem_cap_mb`, `cpus`, `pids_limit`, `measured {rss_mb, cold_start_s, on}`. An empty `measured` means the entry cannot be enabled | E2/E8 |
| `[readiness]`, `[init]`, `[reset]`, `[secrets]` | `kind` (http / tcp / log_then_http / healthcheck), probe, `timeout_s`; typed steps run only by the harness; names generated per run | E5 |
| `[emulator]`, `requires`, `library_requires`, `[grader]`, `[meta]` | Added when an entry first needs them | Later |

**Load-time validation.** This is code, and a failure is a refusal, applied to approved entries too.
- The id regex holds.
- A digest is present for any enabled B/C/D tier.
- The tag is not `latest` and not `*-latest`, even when pinned by digest.
- An image outside T1/T2 has a namespace trust record.
- Env names match `^[A-Z][A-Z0-9_]{0,63}$` and are not in the deny-list: `LD_*`, `PATH`, `HOME`, `NODE_OPTIONS`, `PYTHON*`, `DOCKER_*`, `*_PROXY`.
- There is no free-form argv or flags field.
- Aliases do not collide.
- The licence class agrees with `_licence_watch.toml`.

### 3.4 Uncatalogued open-source services (between runs; switch `SERVICES_USE_LEARNED`)

**Pipeline** (`loop.sh services learn`, run by the operator or the nightly loop)
1. **Need.** The model proposes the upstream `owner/repo` and a docs URL, as schema-only output with no tools. README text is untrusted.
2. **Verify.** Code checks that the repo exists, is not a fork and is not archived.
   - Fetches are https only, on an allowlist: github.com, api.github.com, raw.githubusercontent.com, hub.docker.com, registry-1.docker.io, ghcr.io, quay.io.
   - No redirect may leave the allowlist; resolved IPs are checked against private and link-local ranges; responses are size-capped.
3. **Image refs** must appear verbatim in the fetched docs and are checked with a manifest HEAD.
4. **Trust.** This rule also applies to curated entries:
   - T1: Docker Official.
   - T2: Verified Publisher, or a namespace in `_trusted_namespaces.toml` with an owner record.
   - T3 (a project's own registry) is always `review-needed` and never auto-started, because a typosquat repo passes every automatic T3 check.
5. **Tag.** The newest stable semver that is at least 14 days old; never `latest`, `edge`, `rc` or `nightly`. Pinned by index digest plus host-arch digest.
6. **Licence, per version.** At least two sources must agree: the GitHub licence at the release tag and the OCI `licenses` label.
   - `A OR B` passes on any OSI branch, and the branch used is recorded (for example, Redis 8 via AGPLv3). `A AND B` needs every part.
   - SSPL, BUSL, ELv2, RSAL, PolyForm, Sustainable Use, Commons Clause and "EE" are `blocked-non-osi` unless a class opt-in exists.
   - `NOASSERTION`, disagreement or extra README terms give `review-needed`.
   - Watch rows: Redis ≥7.4 <8, the official Drone image, Nomad, Vault, n8n, Elasticsearch (AGPLv3 option since 8.16 (u), re-checked at pin time).
7. **Size gate before any pull.** Class S ≤150 MB compressed, class M ≤400 MB; anything larger needs an approved entry. The VM free-disk floor (§3.9) must also hold.
8. **Contract learning.**
   - The image config is authoritative: ExposedPorts, Healthcheck, Env, Volumes, User.
   - A value from the docs must cite a span of fetched text, and uncited values are dropped.
   - The model only proposes probe candidates.
   - Docs that need a docker socket get their socket-free mode, or `review-needed`.
   - Every spec goes through the same typed builder as a hand-written entry.
9. **Smoke test in the broker**, on a throwaway `--internal` network, with run limits and `CapDrop ALL`.
   - One capability retry is allowed, within the five-cap set.
   - The probe runs from a pinned sidecar.
   - A behavioural round trip is used where the docs give one; otherwise the entry is marked `listen-only`.
   - The service starts twice, measuring peak RSS and ready time. The lease is `min(class max, ceil(1.5 × peak))`.
10. **Write** `learned/<id>.toml` with provenance. It is listed on `/admin` (HTML-escaped) for approve, block or edit. An owner edit always wins over relearning.

**Timing and caps**
- Learning never runs inside a run or during a Measure batch.
- Each pass learns at most 6 services, with 3 candidates and 6 minutes per service.
- One smoke test runs host-wide at a time, and only when the gate admits its lease.
- `IMAGES` opens on the proxy only for the learner's duration.
- Measure runs pin a catalogue snapshot hash in the settings snapshot.
- `SERVICES_USE_LEARNED` decides whether learned, not-yet-promoted entries are used.
- Intake-time learning is filed (Phase I) until the between-runs learner is measured.

**Rate limits**
- Registry and GitHub responses are cached for 24 h outside agent-writable paths.
- Discovery uses a fine-grained GitHub token with no scopes.
- Pre-pulls use the Docker Hub login the owner names (owner decision #6).
- A pull-through cache (`registry:3`, class S) is optional.

### 3.5 BYO and external services, including Amazon S3

**Connections (Settings > Connections)**
- Each Connection holds:
  - a catalogue id or a custom name;
  - `self-hosted | managed`;
  - non-secret fields in runtime settings;
  - secret fields in the encrypted store, generalising `SETTABLE_SECRETS` (`server/runtime_settings.py:73`) to per-connection keys;
  - the flags `hermetic`, `keep_run_data`, `default_for` and `use_in_build`.
- The connection test runs from harness code:
  - tcp, tls or http(s);
  - s3: HeadBucket, then put, get and delete of a probe object under the run prefix;
  - resp: a raw PING;
  - SQL `SELECT 1` only through drivers the harness already has; anything else gets TCP/TLS.

  It reports pass/fail and the server version, and never echoes a secret.

**Isolation**
- Each run gets a namespace by `byo.isolation`:
  - a `devflow/run_<short>/` bucket prefix;
  - a database or schema `run_<short>`;
  - a keyspace or key prefix.
- The namespace is removed only on a non-resumable ending, or by the retention TTL, and only if `keep_run_data` is unset. A resumable ending (failed, cancelled, pause hand-off, budget pause) keeps it.
- An entry with no isolation kind makes the run `non_comparable`.

**Credentials**
- **How they arrive.** Real credentials reach a run only through a Connection, as `extra_env` to harness-started processes. A run that carries one runs under a proxied uid with the egress allowlist (A12).
- **Who gets them.**
  - Agent build commands get them only when `use_in_build` is set.
  - In-worker graders get them only when `hermetic` is set.
  - Host-side `score.py` never gets them.
- **Where they are kept.**
  - `*_FILE` secrets live in `/run/devflow/secrets/<run>/`, a worker tmpfs directory with mode 0700, owned by the run's uid and written through the A7 helper.
  - The directory is removed at every ending and re-materialised on resume.
  - Credentials are never written to the workspace. They are redacted from sandbox output, transcripts, the ledger and the Sprint Record; only names and fingerprints are kept.
- **What the owner provides.** The form asks for scoped credentials. HANDOVER gets an IAM policy template limited to `arn:aws:s3:::<bucket>/devflow/*`. Root or account keys are never used.
- **Emulator tiers** always get dummy credentials (alphanumeric AWS keys, a `demo-` Firebase project, the Azurite well-known dev key), so an SDK call that goes to the wrong place cannot reach a real account.

**Amazon S3 and other stores for products**
- **Amazon S3:** leave `AWS_ENDPOINT_URL_S3` unset, and set `AWS_REGION`, the keys, `S3_BUCKET` and `S3_PREFIX=devflow/run_<short>/`.
- **Self-hosted S3-compatible stores** (SeaweedFS, Garage, RustFS, R2): the same shape, plus the endpoint and `S3_FORCE_PATH_STYLE`.
- **Azure Blob and GCS:** a BYO connection string or an HMAC key, or tier C/D (Azurite, fake-gcs-server).

**The harness's own store (OS.10)**
- `OBJECT_STORE_PROVIDER=local|s3-compatible|aws`, chosen explicitly. An empty endpoint never means AWS by accident.
- `aws` means:
  - no endpoint, and `OBJECT_STORE_REGION` required (passed through compose; D2);
  - `addressing_style auto`;
  - the harness never creates the bucket;
  - `OBJECT_STORE_PREFIX` lets the store share a bucket;
  - empty keys mean the default credential chain.
- `s3-compatible` means an endpoint plus path style.
- Never MinIO (its archival is (u): check the primary repo).

**Network.** A Connection's host:port is reachable only through that run's proxy allowlist (A12), and nothing else is added.

### 3.6 Licensed services

**Classes:** permissive, copyleft, source-available-free-dev (SSPL, RSAL, BUSL, ScyllaDB SAL, CockroachDB, Redpanda), vendor-free-dev (DynamoDB Local, Google emulators), vendor-dev-licence, saas-only.

| Class | Rule |
|---|---|
| OSI (as a separate network service) | Automatic |
| Source-available-free-dev | One owner opt-in per class, then automatic. Example: SSPL covers MongoDB `mongodb/mongodb-community-server:9.0-ubi9-slim` (u). Without the opt-in: an OSI substitute behind `SERVICES_SUBSTITUTES`, with a recorded gap (FerretDB 2.7 + `postgres-documentdb`, Valkey, OpenSearch, OpenBao), otherwise tier E |
| Vendor-dev-licence | Tier A or E until the VM has 12 GiB or more. The per-entry opt-in and tier-B plumbing are filed (Phase I) |

**Records**
- Each record holds who, when, `terms_url`, edition and limits.
- Only the owner's settings action creates one. The harness, the model and workflow scripts cannot.
- `acceptance_env` is applied only when the record exists.
- A new major version needs a new acceptance. Revoking one makes later runs fall through the tiers.
- Never Enterprise, and never a tag that means EE (Couchbase `latest`, Neo4j `-enterprise`).

**Heavy entries on today's VM resolve to A or E, with a reason.**
- **HANA express:** amd64; 8 GB minimum and 12 GB recommended (u); host sysctl is checked, never set.
  - It goes to HANA Cloud (`<uuid>.hana.<region>.hanacloud.ondemand.com:443`, `encrypt=true`) or to E.
  - CAP over SQLite or Postgres is `abstraction_only`, never a silent swap.
- **Db2 Community:** about 6 GB, needs `IPC_LOCK`/`IPC_OWNER` (u).
- **Oracle Free:** `gvenzl/oracle-free:23-slim-faststart`, about 3 GB (u). It needs a namespace trust record.
- **SQL Server:** a dated CU tag pinned by digest (never `2025-latest`); x86-64 only; `MSSQL_MEMORY_LIMIT_MB=2048`.
- **Keycloak** `start-dev`: class H, about 1.25 GB (u). E1 measures it with a capped heap (`-XX:MaxRAMPercentage`, `KC_CACHE=local`); if it fits in 768 MiB, it becomes class M.

### 3.7 How a product reaches services

- **Only through environment variables:** the entry's `env.vars`, filled from the plan.
  - Secrets go in as `*_FILE` paths under `/run/devflow/secrets/<run>/` where the product supports them.
  - Nothing is written to the workspace. The release `.env.example` carries names only.
- **Run-scoped aliases.** The broker creates `run-<run8>` (`--internal`), starts each service with the alias `<id>-<run8>`, and connects the worker (labelled `devflow.role=worker` in compose) to that network.
  - It reconnects the worker on every worker start and orphan-recovery resume, since a recreate drops the attachments.
  - Two runs are separated by per-run random credentials, per-run uids, and the A8 per-uid rules that reject the other run's network subnet.
- **Injection.**
  - `_child_environment(workspace, extra_env)` gains `service_env_for(workspace)`. On the first product command, it looks up the plan and waits for readiness within the budget.
  - The env reaches agent test and start commands, the acceptance suite's served pass, `start_output`, `start_probe` and the release start, but only for runs with a non-empty plan and an active provider.
  - An empty plan means no vars.
- **Alone start check (always on).** Every run also starts the product once with `PORT`/`DATA_DIR` only, and records whether it boots.
  - With a plan, a failure becomes a defect, with B8's diagnosis.
  - The locked pass for empty-plan families never receives service env (the parity guard).
- **Two-instance check (E9; always on when the plan holds a shared-state service).** Two instances start on different ports against the same plan env. State written through one must be readable through the other; an upload or session that is not is a defect.
- **Product start contract** (a prompt rule from category data, plus a check):
  - one documented command starts every product process (server, workers, scheduler);
  - every setting comes from the environment;
  - schemas, buckets and topics are created idempotently;
  - the first connection retries with backoff, then fails fast, naming the setting.
- **Scoring.** `score.py` runs on the host.
  - It passes a scrubbed, allowlisted environment, never the host `os.environ` (B0.4).
  - Until Phase E, served mode uses a pinned `benchmarks/<b>/hidden/services.compose.yml`. After E, `loop.sh services up <run> --scoring` starts the same catalogue digests with the same spec builder (`src/app/services/spec.py`) on a scoring network.
  - Ports are published on 127.0.0.1 only, are random, and are never 8888, 1234 or 5433.
  - Containers are torn down after scoring.
  - Served scoring needs owner yes #6 and the VM memory check.
  - Hermetic BYO credentials never reach host-side scoring. Containerised scoring is filed (Phase I).
- **Grader reset.** The catalogue `reset` runs before grading and on rewind (drop the run database, `FLUSHDB`, delete the bucket prefix), so build-loop state cannot pass or fail a test.

### 3.8 Isolation

**Per-run network:** `docker network create --internal --label devflow.run=<id>`, with no egress and no published ports.
- A canary on every new network must fail to reach external DNS, `host.docker.internal`, the gateway, 169.254.169.254, a public IP and IPv6.
- If any of those succeeds, services are `environment-unavailable` for the run and the provider is disabled.

**Every service container gets** (body built only by the broker):
- `Memory = MemorySwap = lease` (the lease includes `tmpfs_size_mb`), `NanoCpus`, `CpuShares=256`, `PidsLimit`, `OomScoreAdj=500`;
- `CapDrop ALL` plus the entry's allowlisted `cap_add`;
- `no-new-privileges`, `ReadonlyRootfs` where learned, and a tmpfs data mount with `size=` set;
- logs `max-size=10m,max-file=2` and `RestartPolicy no`;
- labels `devflow.run`, `devflow.role`, `devflow.created` and `devflow.lease_mb`.

**Forbidden in any body:**
- `Privileged`, `Binds`, `Mounts` other than tmpfs, `VolumesFrom`, `Links`;
- `Devices` and `DeviceRequests` (no `--gpus`);
- network, pid, ipc, uts, userns or cgroupns set to host or `container:`;
- `Sysctls`, raised ulimits, `Runtime`, `CgroupParent`, `OomKillDisable`, a negative `OomScoreAdj`;
- `ExtraHosts`, `Dns`, `PortBindings` (except the scoring network on 127.0.0.1), and unconfined `SecurityOpt`.

**The product never gets a socket.**
- The worker keeps `/dev/null` at `/var/run/docker.sock`.
- No `docker` binary is on the product PATH; V1's compose binary sits off PATH.
- Tests assert that the sandbox env and mounts carry no socket and no `DOCKER_HOST`.

**Per-run product uid (A7)**
- **Leasing.** Each run leases a uid from a pool: 10002-10005 open, 10012-10015 proxied (A12). The lease lives in a file-locked table and holds across pool-process churn and resume.
- **The helper.** Commands run through `devflow-run-as`, a small compiled helper with file caps. It:
  - accepts only pool uids and the `workspace` group;
  - clears the bounding set;
  - sets `no_new_privs` on the product process.
- **Workspaces** use group `workspace`, setgid directories and umask 002 for the whole Celery process. appuser joins `workspace`.
- **The worker must never gain `no-new-privileges`,** which would disable the helper. A compose test guards this.

**Egress floor by uid (A8)**
- The one-shot `net-floor` sidecar (`network_mode: service:worker`, `NET_ADMIN`) writes iptables and ip6tables owner-match rules. The worker stays `USER appuser`, with no NET_ADMIN.
- **Open uids are rejected to:**
  - the worker's compose network subnets (127.0.0.11 DNS stays allowed);
  - the host gateway (the owner's :8888, :1234 and 127.0.0.1:5433);
  - 169.254.169.254;
  - the IPv6 equivalents;
  - from Phase E, the other runs' network subnets.
- **Proxied uids** are rejected to everything except loopback and DNS.
- **Everything else stays open for open uids** (for example, registries for installs).
- The rules match subnets, not resolved hosts, so recreating `app` or `db` never makes them stale.

**Reaper**
- It selects on `devflow.*` labels only, for containers **and** networks.
- It runs at broker start, at orphan recovery and every 10 minutes, driven by lease TTLs that the worker renews.
- On resume, it re-adopts a run's containers only if the digest and HostConfig match; otherwise it recreates them and re-runs `init`.
- Rewind runs the `reset` steps.

**Disk.** A 15 GB image quota tracked by digest, LRU pruning after 14 days, and a VM free-disk floor before any pull. Never `docker system prune`.

### 3.9 Resource gate and the owner's GPU models

- **The models are protected by construction.** They run on the host; every service lives in the VM. Raising the VM is the owner's call (recommended: 8 GiB; host swap is full).
  - Services never get `--gpus` or devices.
  - Model-serving entries (Ollama CPU) are class H, with `CUDA_VISIBLE_DEVICES=''`. vLLM is never auto-started.
  - Model tokens/s and latency are read passively from the harness's own model-call telemetry, never by sending probe requests to :8888 or :1234.
- **Admission formula** (all figures in bytes):

  `MemAvailable_VM − reserve − max(0, worker_peak_1h − worker_current) − Σ_granted max(0, lease − usage) ≥ lease`

  - `MemAvailable_VM` is read from `/proc/meminfo` inside the broker.
  - `reserve` is `max(1 GiB, 25% of VM)`.
  - `worker_peak_1h` and `worker_current` are reported by the worker on each `/renew`, from its own cgroup via `tools/resources.py:184`. Both runs share one worker cgroup, so this is a per-worker figure, not a per-run one.
  - Leases live in the broker under a file lock and are rebuilt from `devflow.lease_mb` labels on broker restart.
  - A denied lease waits up to 60 s, then the service steps down a tier with a reason.
  - The gate never stops, resizes or evicts anything.
- **Aggregate CPU cap.** The sum of `NanoCpus` across all service containers is at most 2 CPUs host-wide, to start.
- **Disk floor.** The broker refuses a pull when free space on its root filesystem (the VM disk, (u), confirmed in E1), minus the image size, is below 10 GiB.

| Class | RAM | Ready | On the 4 GiB VM |
|---|---|---|---|
| S | ≤128 MiB | ≤15 s | ≤3 per run, ≤384 MiB per run |
| M | 128-512 MiB (≤768 MiB for a measured JVM entry) | ≤60 s | One per run, if granted (rarely, today) |
| H | 0.5-2 GiB | ≤180 s | Never on 4 GiB; one per host at 12 GiB or more |
| X | Multi-container or privileged | n/a | Never |

- `max_concurrent_pulls_host: 1`. One smoke test at a time, host-wide.

### 3.10 Validating lifecycle files

Rows live in `src/app/stacks/services/_validators.toml`. Each row holds:
- a glob or content sniff;
- tiers;
- the pinned tool, with version and sha256;
- a typed argv;
- pass codes;
- a parser;
- a `not_verifiable` list.

Dependency rows ("if X then Y") also live there as data. `artifact_validators.py` names no technology.

**How validators run.**
- Pinned static binaries in the worker image, run through `SandboxExecutor`, with:
  - an empty env and an empty HOME;
  - a temporary copy of the files;
  - `HTTP(S)_PROXY` pointed at a blackhole;
  - after A12, a proxied uid with an empty allowlist.
- A pre-scan refuses remote references before any tool runs:
  - kustomize URL resources;
  - remote Helm dependencies;
  - compose remote `include:`;
  - OpenTofu URL module sources.

**Core validators (V1):**
- `check-jsonschema --builtin-schema` (github-workflows, gitlab-ci, woodpecker-ci, compose-spec, dependabot) and `actionlint`;
- a standalone `docker-compose` binary, off PATH, running `config -q` with an empty env (it rejects `include:`/`extends:` outside the root, and `env_file:`);
- `kubeconform -strict` with a pinned schema cache plus a pinned CRD schema catalogue (KEDA, Argo, Tekton, ServiceMonitor, cert-manager). A resource without a schema gets `not-verifiable-locally`;
- `helm lint --strict` plus `helm template --kube-version <pin>` (vendored `charts/` only; never `dependency build`);
- `kustomize build --load-restrictor LoadRestrictionsRootOnly` (no plugins, no remote bases, never `--enable-helm`);
- `hadolint`.

**IaC (V6):**
- OpenTofu: `tofu init -backend=false` against a pinned filesystem provider mirror, then `tofu validate`. Providers outside the mirror give `not-verifiable-locally`.
- `tflint`.
- `ansible-lint`.
- A Jenkinsfile is always `not-verifiable-locally`.

**Added by count (V7):** `promtool`, `amtool`, `supercronic -test`, `caddy validate`, `nginx -t`, and `haproxy -c` (refused when `lua-load` is present). Each is added only for file kinds that V0 finds in at least 3 past run workspaces.

**Also covered:**
- The harness's own release workflow (`release.py:37`) and the generated `deploy/services.compose.yml` (B9) go through the same checks.
- Validators that import product code (Airflow DagBag, `dagster definitions validate`) run in the product venv as ordinary test commands.

**Policy assertions** (generic code) on rendered compose and Kubernetes:
- pinned tags;
- a healthcheck or probe is present, with its binary in the image (a gap until tier 3);
- memory limits are set;
- no `docker.sock`, bind mounts, `privileged`, `hostNetwork`, `hostPID`, `hostIPC`, `hostPath`, `hostPort`, `cap_add` or `network_mode: host`;
- `allowPrivilegeEscalation: false` and `runAsNonRoot`.

**Verdicts per file and tier:**
- `pass`;
- `fail` (file, line, message);
- `not-verifiable-locally` (OIDC, hosted cache, cloud credentials, macOS/Windows runners, remote fetch, missing CRD schema or provider);
- `environment-unavailable`.

Release gaps say "validated to tier N of M", and a step that did not run is never reported as a pass. Failures are non-blocking notes until `ARTIFACT_FINDINGS_AS_DEFECTS` is measured. Tiers 2-3 and building the product image are filed (Phase I).

### 3.11 Starter catalogue across the lifecycle

Every version, image size and RSS figure below is (u). Each is resolved from the registry and measured on this host when it is pinned at E8.

| Need | Default entry (class) | Licence | When not allowed or not fitting |
|---|---|---|---|
| SQL | `postgres:18.6-alpine` (S), tmpfs at `/var/lib/postgresql` | PostgreSQL | MySQL 8.4 / MariaDB 12 (M) |
| Cache, Redis protocol | `valkey/valkey:9.1-alpine` (S) | BSD-3 | `redis:8.x-alpine` (AGPL branch) when Redis 8 features are named |
| Document | MongoDB 9.0 ubi9-slim (M), after the SSPL opt-in | SSPL | FerretDB 2.7 (switch) or E |
| Object storage | SeaweedFS `weed mini` (S/M; `chrislusf` trust record) | Apache-2.0 | Garage ≥2.3 `--single-node` (AGPL); BYO |
| Object storage, Azure / GCS | Azurite (S/M, tier C); fake-gcs-server (S, tier D) | MIT / BSD-2 | BYO |
| Mail | Mailpit (S; `axllent` trust record) | MIT | n/a |
| Identity | Ory Hydra (S, real OIDC); Dex (S); `navikt/mock-oauth2-server` (M; trust record) | Apache-2.0 / MIT | Keycloak `start-dev` (H, or M if E1 fits it in 768 MiB); Auth0/Okta/Entra → BYO |
| SAML / LDAP | BoxyHQ mock-saml (S); lldap (S) or OpenLDAP (S) | Apache-2.0 / GPL-3.0 / OpenLDAP | BYO |
| Queues | NATS 2.x (S), Mosquitto (S), RabbitMQ 4.x (M), `apache/kafka-native:4.x` (M) | Apache-2.0 / EPL-2.0 / MPL-2.0 | ElasticMQ (S) for SQS; Redpanda (BSL class opt-in); never LocalStack (token, non-commercial) |
| Cloud emulators | moto server (S/M); DynamoDB Local (M); Pub/Sub emulator (M); Service Bus emulator (H, needs a SQL Server container) | Apache-2.0 / vendor-free-dev | BYO or E |
| Jobs and workflows | Libraries map to brokers via `library_requires` (Celery, RQ, BullMQ, Sidekiq OSS, pg-boss, graphile-worker); Temporal dev (S); Hatchet-lite + Postgres (M) | MIT / BSD | Airflow (X) → DagBag plus `dags test` in the venv; n8n and Restate by opt-in only |
| Schedulers | `supercronic` in the product image; Ofelia `job-local` INI only | MIT | n/a |
| Search | Meilisearch CE (S/M); Typesense | MIT / GPL-3.0 | OpenSearch (H); Solr (M); Elasticsearch after the AGPL re-check (H) |
| Secrets | OpenBao dev (S); SOPS | MPL-2.0 | Vault (BUSL) → opt-in |
| Observability | OTel collector (S), Jaeger v2 (S/M), Prometheus (M) | Apache-2.0 | Loki, Tempo, Grafana (AGPL, M) |
| Gateways | Caddy, nginx, HAProxy, Traefik (S); APISIX standalone (M); `kong:3.9` OSS | OSI | Never `kong-gateway:3.10+` |
| Feature flags | `unleash-server` OSS, Flagsmith (M + Postgres) | Apache / BSD | GrowthBook needs MongoDB (SSPL) |
| Vector and ML | pgvector `0.8-pg18` (S), Qdrant, Chroma, MLflow (M) | OSI | Milvus (X) → milvus-lite or pgvector (gap) |
| CI/CD, registry, forge | registry:3 / Zot (S); Forgejo or Gitea (M), as tier-3 targets only | OSI | GitLab CE (X): never |
| Scaling | The two-instance check (E9); compose `--scale` (tier 3, filed); HPA and KEDA validated statically against the CRD catalogue | n/a | kind and k3d: never on this VM |

---

## 4. How the container runtime is reached safely (the central decision)

**The constraint.** Product code runs inside the worker. Whoever starts containers holds an API equivalent to root on the Desktop VM, and the VM shares host directories. E1 confirms whether a create with binds under `/home` would succeed.

| Option | Verdict |
|---|---|
| Socket in the worker | **Rejected.** The product would become root on the VM |
| Repaired `container` mode (one container per command) | Not now. It needs the socket in the worker and has rotted. Filed as Phase I |
| Privileged DinD, or kind/k3d in the VM | **Rejected.** Privileged, re-pulls, does not fit the VM; `hostPath: /` reaches all containers |
| Socket proxy with the worker as its client | **Rejected.** It filters paths, not bodies, so a privileged create with binds still passes |
| Sysbox or gVisor on Docker Desktop | Not installed (u). Filed |
| Rootless engine (Podman or dockerd) under a dedicated host user, using the host's 43-48 GB, with 127.0.0.1 port ranges and per-port A8 exceptions | Strongest isolation, and room for class M/H. But the worker cannot join its networks, and it touches the owner's host beside the GPU models. An **option for the owner** (yes #14); filed for tiers 2-3 and Phase I |
| **Harness-owned broker plus a socket proxy** | **Chosen** |

**Components** (new compose services under the `services` profile; nothing in the product path changes)

1. **`svc-proxy`**
   - **Image.** E1 chooses between `tecnativa/docker-socket-proxy` and a method-and-path regex proxy (for example `wollomatic/socket-proxy`, (u)), pinned by digest with a namespace trust record. It is the **only** container with `/var/run/docker.sock` (read-only).
   - **Networks:** `svc-control` only (internal). No ports, 64 MiB.
   - **With tecnativa:**
     - allowed: `CONTAINERS`, `NETWORKS`, `POST`, `INFO`, and `IMAGES=${SVC_PROXY_IMAGES:-0}` (1 only while the learner runs);
     - denied: `EXEC`, `VOLUMES`, `BUILD`, `SWARM`, `SERVICES`, `SECRETS`, `PLUGINS`, `SYSTEM`, `SESSION`, `DISTRIBUTION`;
     - `CONTAINERS` plus `POST` still allows update, kill, stop and archive PUT on **any** container, including the owner's 21 others.
   - **With a regex proxy:** only create, start, stop, delete and inspect on containers; create, connect, disconnect and delete on networks; `GET /info`; image inspect; and image create while the learner runs. Even so, container ids are not label-scoped.
   - **Either way, the broker's code is the boundary for every container on the engine.**
2. **`svc-broker`**
   - The harness image running `python -m app.services.broker`, as a non-root uid with `cap_drop: [ALL]`, `read_only`, tmpfs `/tmp` and 256 MiB.
   - Its env holds **only** `BROKER_TOKEN`, the proxy URL and limits: no DB, JWT, provider, object-store or operator secrets.
   - **Networks:** `svc-control` and `default`. It joins a run network only for init, reset and probe.
   - Every Docker call has a timeout. `ensure()` never blocks a product command beyond its budget.
3. **API** (typed: callers pass no argv, images or flags)
   - `POST /runs/{run}/ensure {plan_id}`, `/reset`, `/release`, `/renew {worker_peak, worker_current}`;
   - `GET /runs/{run}/status`, `GET /health` (it reports the broker's image id and catalogue hash);
   - `POST /learn {name, quote}`, used by `loop.sh services learn` only.

   The broker re-reads the plan and re-resolves each id against its own catalogue copy. Caps: 6 services per run and 8 minutes of provisioning per run.
4. **Body safety**
   - `spec.build(entry, run)` builds the body from typed fields, with the Healthcheck in the body (EXEC is denied).
   - `spec.validate(body)` re-checks §3.8 before create.
   - After create, `inspect` compares HostConfig and removes the container on any difference. The same check runs on re-adoption.
5. **Worker connection.** `network connect` accepts only the container labelled `devflow.role=worker` (a compose label). The broker re-attaches it on every worker start and resume.
6. **Pre-pull.** `loop.sh services prepull` uses the Docker Hub login the owner names, on the host (owner decision #6; the harness operator account is not a Docker Hub credential).
   - It runs nightly or before Measure.
   - No registry credential enters a container.
   - Nothing is pulled during a run.
   - An absent digest steps down with "not pre-pulled".
7. **Deploy.** `loop.sh deploy` and ship-live bring up `svc-proxy` and `svc-broker` with `--profile services` (and `seaweedfs` with `--profile storage`) when those profiles are enabled. ship-live's stale-image check covers the broker.
8. **`loop.sh ready`** reports broker and proxy state within a fixed timeout, and never hangs on a dead broker. It fails when the broker's image id or catalogue hash differs from the worker's. When the broker is absent, the provider is `none`, and every service resolves to A, D or E with that reason (not counted as `environment-unavailable`).

**Privilege, plainly:**
- One container holds root-equivalent access to the VM.
- A compromised or buggy broker could create a privileged container from a present image, or stop, update or write into any container on the engine.
- The controls are:
  - the typed builder;
  - validate-then-inspect;
  - the label reaper;
  - an env with no secrets;
  - the E1 proxy choice.
- The token is not the boundary. After A7, product uids cannot read it, and A8 rejects the compose subnet, which `svc-broker` sits on.

**Owner approvals before Phase E** (none assumed): rows 3-7, 9 and 14 in §7.

---

## 5. Phases in build order

**Rules for every item**
- **Tests.**
  - Every fix has a test proven to fail on the old code (run against `git stash`).
  - Test files are named as sentences (`tests/test_<sentence>.py`).
  - Every prompt rule gets `test_the_rule_bans_the_product_words`, banning the whole words task, tasks, to-do, todo, button, click and checkbox. "Ban test" in the tables means this test.
  - `scripts/loop/loop.sh suite` must be fully green, with `src/` untouched while it runs.
- **Records and commits.**
  - One Appendix M row per fix, starting at **LF.788**, each in its own commit.
  - Every commit is followed by `git push main harness-hardening-session`, with STATE and both handovers in the same commit.
- **Deploys.**
  - Deploys happen at run boundaries: `loop.sh deploy`, then `loop.sh ready` must print ALL READY. One deploy per bundle.
  - After a pack change, run `docker compose run --rm -T --no-deps worker python - < scripts/loop/verify_packs.py` on the changed packs (LF.719).
  - New compose services (`net-floor`, `seaweedfs`, `svc-proxy`, `svc-broker`) get an explicit `compose_up.sh` step with their profile in `loop.sh deploy` and ship-live.
- **Hygiene.**
  - No run ids in code, comments, prompts or tests.
  - Every commit that touches `docker-compose.yml` stages with `git add -p`. The A11 guard refuses a staged hunk containing `5433`.
- **Switches.** A new switch needs all of:
  - a module with `ON_BY_DEFAULT=False` and `enabled()`, listed in `src/app/observability/provenance.py:22 SWITCHES`;
  - membership in `src/app/switches.py` `GROUPS` (`:144`) or `BUNDLES`;
  - a `NAME: ${NAME:-off}` line in compose `x-app-env` (`tests/test_every_group_2_switch_reaches_the_worker.py`);
  - a `docs/measuring.md` row (`tests/test_every_switch_has_a_row_in_the_register.py`);
  - a firing signal for `loop.sh effects`.

  A switch is registered only when its module exists.

### Phase A: remaining truth and safety (always on; about 10 days)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **A11** Repo guards | `scripts/loop/guard_staged.sh` (refuses a staged hunk containing `5433`); `.githooks/pre-commit`; `loop.sh hooks` (sets repo-local `core.hooksPath`; `loop.sh suite` warns when unset); `scripts/loop/ship_live.sh:19` reads the login line after a `<!-- operator-login -->` marker in `docs/HANDOVER.md`, not `sed -n 65p`; the run id removed from the compose comment | `test_the_commit_guard_refuses_the_owner_port_hunk`; `test_ship_live_finds_the_login_after_lines_are_inserted` (fixture file, nothing printed); `test_compose_names_no_run_id` | Always on | Guard fires on a scratch staged hunk; ship-live's lookup returns the marked line |
| **A9** Close the full-environment leaks | `src/app/acceptance/start_probe.py:76-79` and `src/app/acceptance/spec_dry_run.py:92` build their env from `sandbox._child_environment` plus `PORT`/`DATA_DIR` | `test_start_probe_env_carries_no_worker_secret`; `test_spec_dry_run_env_carries_no_worker_secret` (a sentinel secret placed in `os.environ` must be absent); `test_no_product_subprocess_inherits_the_worker_env` (static scan: every `subprocess`/`Popen` in `src/app/acceptance` and `src/app/tools` passes `env=`) | Always on | tasks-api sentinel: the start probe still passes |
| **A10** Fresh-install execution mode | `docker-compose.yml:106`, `.env.example:176` (and mode resolution in `sandbox.py` if needed) | `test_fresh_install_mode_runs_without_a_socket` (compose defaults with `DOCKER_SOCKET=/dev/null` must execute a product command). If it passes on old code because a fallback exists, the item closes with no change | Always on | Default config works with a `/dev/null` socket; the live host is unchanged |
| **A3** Harness Redis password and pin | `docker-compose.yml:24` (`redis://:${REDIS_PASSWORD}@redis:6379/0`); `:212-222` (`--requirepass`; healthcheck via `REDISCLI_AUTH`; image pinned by digest to Redis 8 on the AGPLv3 branch, which loads the existing 7.4 AOF (u, spike), or Valkey after a recorded flush at a boundary); `scripts/setup-env.sh` (`add_if_missing REDIS_PASSWORD "$(genpw)"`, passed to `redis` only); `model_ready.py` (`loop.sh:480`) fails closed when `REDIS_URL` carries no credential (parsed, never printed); `tests/conftest.py:254`; `loop.sh deploy --with-redis` (hold, stop app and worker, recreate redis, start app and worker, ready) | `test_compose_redis_needs_a_password` (requirepass; the URL carries a credential; the healthcheck authenticates); `test_harness_redis_pinned_by_digest_outside_the_licence_watch`; `test_setup_env_generates_redis_password`; `test_ready_refuses_a_redis_url_without_a_credential`; `test_product_env_never_carries_worker_secrets` (scoped to the worker's own variable names **and values**, across `_child_environment`, `start_probe` and `spec_dry_run`; plan-injected names are allowed) | Always on | `.env` regenerated (no values printed); ALL READY; Celery connects in a tasks-api sentinel; the AOF loaded or the flush recorded. Ships in the A7 boundary deploy; if A7 slips, it ships alone, labelled defence in depth |
| **A7** Product commands under a per-run uid | **Spike (half a day):** file caps on Desktop overlayfs; git `safe.directory`; npm, pip and uv cache homes; deleting tarball-extracted directories; Playwright relocation. **Then:** `docker/devflow-run-as.c` (a Dockerfile build stage; accepts only pool uids and gid `workspace`; setgroups, setresgid, setresuid; clears the bounding set; sets `no_new_privs`; modes `--exec`, `--signal <sig> --pgid\|--all`, `--fix-perms <path under the workspace root>`), installed at `/usr/local/libexec/devflow-run-as` with mode 0750 `root:appuser` and `cap_setuid,cap_setgid,cap_setpcap=ep` (adds `libcap2-bin` at build); `Dockerfile` (uids 10002-10005, group `workspace`, appuser in `workspace`, `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` group-readable, the shared download cache at `:156-160` group-writable setgid, system `safe.directory` for the workspace root); `src/app/tools/uid_pool.py` (file-locked per-run lease, held across pool churn and resume, released at a final ending once no process of that uid remains); `sandbox.py` (`_execute_here` `:4918` adds the argv prefix and a per-run HOME; umask 002 set at Celery start; `killpg` at `:1288` via the helper); `acceptance/stray_services.py:38,47` (finds strays by world-readable `/proc/<pid>/status` Uid mapped through the lease table, plus a harness-written process registry; kills via `--signal --all`); `start_probe.py:100` and `spec_dry_run.py` run through the helper; the cleanups (`manage.py:1231-1240`, rewind/restore, `start_output.py:186-189`) call `--fix-perms` first; `manage.py workspaces --regroup` (one-off); `model_ready.py` live probe, and `CELERY_CONCURRENCY` ≤ pool size | `test_product_argv_runs_as_the_run_uid`; `test_two_live_runs_get_different_uids`; `test_uid_lease_survives_pool_process_churn`; `test_concurrency_above_the_pool_is_refused_by_ready`; `test_run_as_helper_refuses_uids_outside_the_pool` (0, 10001); `test_product_process_holds_no_capabilities` (CapEff, CapPrm and CapBnd all 0; NoNewPrivs 1); `test_run_as_helper_not_executable_by_product_uid`; `test_worker_has_no_no_new_privileges` (compose); `test_stray_scan_finds_product_uid_process_without_reading_environ`; `test_timeout_kill_reaches_a_product_uid_group`; `test_workspace_cleanup_deletes_product_made_read_only_dirs`; `test_agent_written_lockfile_writable_by_product_uid`; `test_playwright_browsers_readable_by_product_uid`; live probe: a product command reading `/proc/1/environ` is refused (fails on the old image) | Always on | Own image rebuild and deploy at a boundary; tasks-api, notes-api-hono and one UI-family sentinel (browser present) show no regression; strays cleaned. **Required before any BYO credential or broker token lives in the worker.** Sentinels re-baselined (P0b) |
| **A8** Egress floor by uid (owner yes #2) | **Spike (half a day):** `xt_owner` in the VM kernel; iptables-nft vs legacy; IPv6 presence; the host gateway IP; whether `host.docker.internal` reaches host-loopback ports. **Then:** `Dockerfile` (adds `iptables`); `docker/net-floor.sh`; compose `net-floor` (harness image, `user: "0"`, `cap_add: [NET_ADMIN]`, `network_mode: "service:worker"`, `restart: "no"`, profile `floor`), while the worker stays `USER appuser` with no NET_ADMIN; `src/app/services/egress.py` (rule generator: pool uids rejected to the worker's compose subnets (keeping 127.0.0.11 DNS), the host gateway, 169.254.169.254 and the v6 equivalents); `loop.sh deploy`, ship-live and `compose_up.sh` run `net-floor` after every worker (re)create; `sandbox.py` makes product commands wait up to 60 s for the floor probe, then pauses the run with "egress floor absent"; live probe in `model_ready.py` | `test_floor_rejects_the_compose_subnet_not_resolved_hosts`; `test_floor_rejects_host_gateway_and_metadata`; `test_floor_covers_ipv6`; `test_worker_keeps_appuser_and_no_net_admin`; `test_deploy_reapplies_the_floor_after_worker_recreate`; `test_product_command_waits_for_the_floor`; live probe: a product uid to `host.docker.internal:1234` and `db:5432` is refused, and a registry is reachable | Always on | The owner's model ports and harness services are unreachable from product code; installs still work |
| **A12** Allowlist egress for credential runs | `Dockerfile` (proxied pool, uids 10012-10015); `egress.py` (proxied uids rejected everywhere except loopback and DNS: static rules, applied by `net-floor`); `src/app/services/egress_proxy.py` (a loopback HTTP CONNECT proxy run by the worker as appuser; per-run proxy credential; allows the run's pack install hosts and its Connection host:port, plus per-run loopback TCP forwarders for non-HTTP Connections (u)); `INSTALL_HOSTS` in each stack pack under `src/app/stacks/packs/`; `_child_environment` sets `HTTP(S)_PROXY`/`NO_PROXY` for proxied runs; `uid_pool.py` picks the proxied pool when the plan holds a real credential | `test_run_with_a_real_credential_gets_a_proxied_uid`; `test_proxy_refuses_a_host_outside_the_run_allowlist`; `test_proxy_credential_of_one_run_refused_for_another`; live `test_proxied_uid_has_no_direct_egress` | Always on (forced whenever a real credential is in the plan) | A stub-Connection run installs packages through the proxy and reaches only its declared host. SDKs that ignore proxy env (u) are a recorded risk, measured in Phase C |

**Order:** A11, A9, A10 (one bundle) → A7 + A3 (one boundary deploy and image rebuild) → A8 (after yes #2) → A12 (before Phase C uses a real credential).

### Phase B0: measurement families (benchmark files and scoring; no `src/`; about 3.5 days)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **B0.1** `benchmarks/files-api/` | The brief names S3 attachments (Amazon S3 in production), a Redis cache and rate limit, OIDC sign-in (Keycloak in production) and email on share. It **fixes the dev-issuer API** (issuer path, token endpoint, claim names) so hidden tests do not depend on product choices. `bench.json` gains `modes: ["alone","served"]`; `hidden/conftest.py` copied from tasks-api; `hidden/alone/` holds 8 tests (upload round trip, rate limit, dev-issuer token accepted, forged token rejected, share outbox through the API, restart persistence); `hidden/served/` holds 9 tests (objects visible through a harness S3 client, mail visible through the Mailpit API filtered by run, a two-instance upload-then-read, and the rest); `reference/` | `test_the_files_api_bench_reference_scores_full` | Benchmark | Reference scores 17/17 |
| **B0.2** `benchmarks/jobs-api/` | The brief names Postgres and a Redis-protocol broker, and asks for a compose file and a CI workflow. `hidden/served/` holds 10 tests (enqueue to done, failure with retry count, dead letter, no double processing with two workers, a scheduled job, restart persistence, broker loss gives an error or retry rather than a hang); `hidden/artifacts/` holds 3 tests (actionlint, compose config plus policy, healthcheck binary) | `test_the_jobs_api_bench_reference_scores_full` | Benchmark | Reference scores 13/13 |
| **B0.3** `score.py` modes | `scripts/bench/score.py` copies `hidden/<mode>/` when `bench.json` has `modes` (today it copies only `hidden`, at `:268`; existing families are unchanged). Served mode starts the pinned `hidden/services.compose.yml` (127.0.0.1, random ports, never 8888/1234/5433, torn down after) only after owner yes #6, and only when the VM's MemAvailable (read through the worker's `/proc/meminfo`) minus 1 GiB covers the compose's summed `mem_limit` | `test_scoring_services_never_publish_owner_ports`; `test_served_scoring_refused_when_vm_memory_short`; `test_existing_families_keep_the_hidden_layout` | Always on | Both new references score full in every mode |
| **B0.4** Scrubbed scoring env | `score.py` `_run` (`:51-52`) passes an allowlisted env (`PATH`, `LANG`, a temporary `HOME`, `PORT`, `DATA_DIR`, `PRODUCT_DIR`, plus plan vars in served mode) instead of the host `os.environ`, which reaches the product through `hidden/conftest.py:29`. BYO credentials are never passed | `test_scored_product_env_is_scrubbed`; `test_host_scoring_never_gets_byo_credentials` | Always on | Sentinel reference scores unchanged |

**Acceptance**
- A family is a `benchmarks/<name>/` directory read by `loop.sh bench` through `bench.json` (`held_out_since`, `base`; `loop.sh:171-188`); there is no registry.
- The P0 Measure pair runs on a frozen SHA: files-api ×2, plus the sentinels tasks-api ×2 and notes-api-hono ×2. It is recorded in `docs/measuring.md`.

### Phase B: resolver core, service plan, tiers 0 and E everywhere (always on, quality; about 5 days)

Prerequisite: the owner's ruling on open question 1.

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **B1** Catalogue loader and schema | `src/app/services/catalogue.py`; `src/app/stacks/services/_categories.toml`, `_trusted_namespaces.toml`, `entries/*.toml` (data only, `real` disabled until measured): postgres, valkey, redis, memcached, mailpit, seaweedfs, azurite, fake-gcs-server, ory-hydra, dex, mock-oauth2-server, keycloak, mock-saml, lldap, openldap, mongodb, ferretdb, couchdb, dynamodb-local, moto, elasticmq, pubsub-emulator, servicebus-emulator, rabbitmq, nats, mosquitto, redpanda, meilisearch, solr, temporal-dev, openbao, hana, oracle-free, mssql, db2 | `test_catalogue_rejects_bad_id_env_and_free_flags` (`../x`, `LD_PRELOAD`, `DOCKER_HOST`, an enabled tier with no digest); `test_alias_collisions_refused`; `test_every_shipped_entry_loads`; `test_curated_image_outside_t1_t2_needs_a_trust_record`; `test_floating_tag_refused_even_with_digest`; `test_services_code_names_no_service` (no id or alias in `src/app/services/*.py`) | Always on | Every entry loads |
| **B2** Licence gate (static) | `src/app/services/licence.py`; `stacks/services/licences/spdx.json`, `_licence_watch.toml` (Elasticsearch row re-checked at pin time) | `test_spdx_or_and_matrix` (including `ELv2 OR SSPL OR AGPL-3.0` passing on the AGPL branch); `test_busl_sspl_elv2_rsal_blocked`; `test_noassertion_review_needed`; `test_redis_7_4_blocked_7_2_and_8_pass`; `test_redpanda_bsl_needs_class_opt_in`; `test_vendor_dev_licence_without_record_never_tier_b` | Always on | The watch list matches the catalogue |
| **B3** Needs extraction | `agents/tools_models.py` (`backing_services: list[ServiceNeed{name, role, quote}]`); `agents/stack_selector.py` (records only quoted needs); `src/app/services/needs.py` (deterministic alias scan over the brief, `database` (`:55`) and `additional_tools` (`:57`)). `stacks/__init__.py:776` `aligned_stack` already keeps new fields, so it needs no change, and a test guards it | `test_unquoted_service_dropped`; `test_alias_scan_finds_named_service` (model stubbed to return none); `test_aligned_stack_keeps_services`; ban test | Always on | A brief naming Redis yields a quoted need |
| **B4** Resolver, plan, ledger | `src/app/services/{resolver,plan,ledger}.py`; `server/runner.py` (resolve after stack selection; plan in the settings snapshot) | `test_unknown_service_goes_to_tier_e_with_catalogue_request`; `test_tier_reason_recorded`; `test_licence_not_accepted_never_silent_substitute`; `test_required_real_unmet_refuses_run`; `test_model_invented_image_never_in_plan`; `test_empty_plan_for_existing_briefs`; `test_hana_on_small_vm_resolves_byo_or_e_with_reason`; `test_mssql_refused_on_arm64` | Always on | Existing families' briefs give empty plans |
| **B5** Contract and specification | `src/app/agents/environment_contract.py` (generated services paragraph: names, tier, fallback; the "no way to start one" text at `:138`/`:224` only for an empty plan); `src/app/agents/specialists.py:601` `describe_stack` ("category: name - read SETTING; when unset, use SHAPE"); `src/app/graph/workflow.py:1459` `_the_database_section` → `_the_services_section` (used at `:11397`); the `seed.py:50-59` postgres sentence becomes conditional | `test_contract_text_unchanged_for_empty_plan`; `test_contract_lists_plan_vars_and_tier_never_secrets`; `test_spec_may_not_demand_unplanned_service`; ban test | Always on | The contract text is identical for an empty plan |
| **B6** Seed rows and extractor aliases | `plugins/seed.py` (rows per id: setting, fallback, retry; `SERVICE_ALIASES`); `plugins/middleware.py:364` (append planned ids, filtered by `_turned_down_by_the_selected_stack` at `:351`) | `test_extractor_adds_planned_service_keyword`; `test_turned_down_alias_not_added`; ban test on the service rows | Always on | A planned id's seed row fires |
| **B7** Pack fallback shapes | `stacks/packs/_service.py:184` `DATA_GUIDE` and `stacks/packs/_fullstack.py:656` `DATA_GUIDE` (both from categories); `fullstack_next.py`; `fullstack_django.py` (locmem cache; file mail unless `SMTP_URL`); `ruby_rails_api.py` (`:memory_store`, `:async`, `:file`) | `test_pack_service_defaults`; then `verify_packs` on the changed packs | Always on | `verify_packs` green |
| **B8** Start diagnosis, alone check, start contract | `acceptance/suite.py`; `acceptance/start_output.py:151` ("requires <SETTING>; with it unset, use <shape> or fail naming it", from a named setting or a refused default port); `analysis/integration_checks.py` (a client package whose category the stack lacks); the alone start check; one-command start when the plan has a queue | `test_start_log_redis_url_required_names_setting`; `test_refused_default_port_is_named`; `test_client_package_without_category_flagged`; `test_alone_check_runs_without_service_env`; `test_locked_pass_never_receives_service_env`; `test_queue_plan_start_without_worker_noted`; ban test | Always on | The boots-alone KPI is recorded on every run |
| **B9** Release gaps and self-host files | `stacks/release_docs.py` ("Backing services" section; writes `.env.example` with names only (new); writes `deploy/services.compose.yml` from the plan's digests and env names, validated by V; Helm values only when the product ships a chart); `release_audits.py` (licences listed) | `test_release_lists_tier_e_gap`; `test_env_example_has_names_no_values`; `test_release_services_compose_uses_plan_digests`; `test_release_services_compose_passes_policy` (after V3) | Always on | A served-family release carries a runnable services compose |
| **B10** `_on_terminal(record)` | `server/runner.py`: one path for every ending. Every ending archives: complete/failed (`:1691`), exception (`:1561-1575`), identical-gate fail (`:1826`), stalled (`:1915`), `MAX_GATES` (`:1944`), cancelled (`:2083`). Release and BYO namespace deletion happen only on non-resumable endings: not in `RESUMABLE_STATUSES` (`:245`), not the pause hand-off (`:2084-2086`), not `BUDGET_PAUSE_STATUS` (`:1572`, `:1714`). Resumable endings keep leases until the reaper's TTL | `test_cancelled_run_is_archived`; `test_gate_exhausted_run_is_archived`; `test_identical_gate_fail_is_archived`; `test_stalled_run_is_archived`; `test_exception_ending_is_archived`; `test_resumable_ending_keeps_services_and_namespace`; `test_pause_hand_off_never_releases`; `test_budget_pause_never_releases` | Always on | A cancelled and then resumed run keeps its state |

**Acceptance**
- The sentinels show no regression and are re-baselined on the new SHA.
- P1 Measure pair: files-api ×2 and jobs-api ×2 (tier E).
- The alone score or the boots-alone KPI should move against P0. If nothing moves, audit the B8 notes before parking anything; these are quality fixes and stay on.

### Phase C: BYO connections and Amazon S3 for products (plumbing always on; using it is the owner's choice; about 2.5 days)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **C1** Connections store and page | `src/app/services/connections.py`; `server/runtime_settings.py:73` (per-connection encrypted secrets); settings API and a "Connections" page | `test_connection_secret_never_returned`; `test_connection_secret_encrypted_at_rest` | Always on | A connection saved and listed without its secret |
| **C2** Connection test | `src/app/services/probes.py` (tcp, tls, http, s3, resp; SQL only through existing drivers) | `test_s3_probe_uses_run_prefix_only` (stubbed); `test_unknown_service_probe_is_tcp_tls_only`; `test_probe_never_echoes_secret` | Always on | A stub S3 passes the probe |
| **C3** Tier A, per-run namespace, file secrets | `resolver.py`; `src/app/services/providers/byo.py` (create and drop through `byo.isolation`; `keep_run_data`; drop only on non-resumable endings or by TTL); compose worker tmpfs `/run/devflow` (`git add -p`); `*_FILE` secrets written through the A7 helper | `test_byo_maps_to_same_env_as_tier_b`; `test_byo_namespace_removed_on_final_ending_only`; `test_no_isolation_marks_non_comparable`; `test_emulator_tiers_get_dummy_cloud_keys`; `test_file_secrets_live_outside_the_workspace_0700_run_uid`; `test_file_secrets_removed_at_every_ending_and_rematerialised_on_resume` | Always on | Namespace created and dropped on a stub |
| **C4** Secret redaction | Sandbox output path, transcript writer, ledger, Sprint Record | `test_service_secret_redacted_from_command_output_and_record` | Always on | No secret in any record |

**Acceptance.** C needs A7 and A12 first. If the owner provides an Amazon S3 or self-hosted S3 Connection, one files-api run uses it:
- objects land under `devflow/run_<short>/` and are removed at the final ending;
- the run is `non_comparable` and audited by hand;
- it is not scored by host-side `score.py`;
- whether the product's S3 SDK honoured the proxy env is recorded.

### Phase V: lifecycle file validation, tiers 0-1 (always on; findings non-blocking; parallel with C; about 3.5 days)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **V0** Count file kinds | `scripts/loop/count_artifact_kinds.py` (read-only scan of past run workspaces, by glob or sniff) | `test_counter_classifies_fixture_workspace` | Tool | Counts recorded in `docs/measuring.md` |
| **V1** Core validators in the image | `Dockerfile` tool stage with sha256-verified downloads (actionlint, kubeconform plus pinned schema cache and pinned CRD catalogue, helm, kustomize, hadolint, standalone `docker-compose` at `/opt/validators/bin`, off PATH); `check-jsonschema` in a tool venv; `_validators.toml` | `test_validator_rows_pinned_by_version_and_sha256`; `test_every_row_has_valid_and_invalid_fixture` (`tests/fixtures/artifacts/`); `test_no_docker_binary_on_the_product_path`; `test_crd_without_schema_is_not_verifiable` | Always on | Image size growth recorded |
| **V2** Runner, no network | `src/app/acceptance/artifact_validators.py` (empty env, empty HOME, temp copy, timeouts, blackhole proxy, remote-reference pre-scan; a proxied uid with an empty allowlist after A12) | `test_kustomize_argv_never_enables_plugins_or_helm`; `test_helm_without_vendored_charts_is_not_verifiable`; `test_compose_interpolation_gets_empty_env`; `test_validator_env_carries_no_harness_secret`; `test_remote_refs_refused_before_running`; `test_validators_get_a_blackhole_proxy` | Always on | Fixtures pass and fail as expected |
| **V3** Policy assertions and dependency rows | The same module (generic policy code); dependency rows (BullMQ ≥6 needs ioredis; RQ 3 needs `TZ=UTC`; a Redis-protocol queue broker needs `maxmemory-policy noeviction`) as data in `_validators.toml`, fed forward through `seed.py` rows | `test_compose_bind_mount_or_privileged_rejected`; `test_k8s_hostpath_rejected`; `test_healthcheck_binary_missing_flagged`; `test_dependency_row_flags_missing_library` (fixture: BullMQ without ioredis); `test_validator_code_names_no_technology`; ban test | Always on | jobs-api reference passes policy |
| **V4** Verdicts to release gaps | `release.py`, `release_docs.py` (the harness's own CI file and `deploy/services.compose.yml` validated) | `test_release_ci_workflow_validated`; `test_unrun_tier_never_reported_as_pass`; `test_not_verifiable_becomes_gap` | Always on | Release says "validated to tier N of M" |
| **V5** Tier 0-1 `fail` becomes a defect in the fix loop | `graph/workflow.py` defect intake | `test_validator_fail_raises_defect_when_switch_on` | **`ARTIFACT_FINDINGS_AS_DEFECTS`** (off; measured on jobs-api, since it costs fix rounds) | P4 |
| **V6** IaC and Jenkinsfile | Tool stage: OpenTofu plus a pinned filesystem provider mirror (providers chosen from the V0 counts), tflint; `ansible-lint` in the tool venv; rows in `_validators.toml`, including Jenkinsfile as `not-verifiable-locally` | `test_tofu_runs_without_backend_or_network`; `test_provider_outside_mirror_is_not_verifiable`; `test_ansible_lint_row_fixture`; `test_jenkinsfile_is_not_verifiable` | Always on | Fixtures pass and fail as expected |
| **V7** Count-gated validators | promtool, amtool, supercronic, caddy, nginx, haproxy (`lua-load` refused), each added only when V0 counts its kind in at least 3 past runs | `test_every_row_has_valid_and_invalid_fixture` covers each added row | Always on | Only counted kinds added |

**Deploy:** one image rebuild at a run boundary, with the size growth recorded.

### Phase D: object storage OS.0-OS.8 plus OS.10 (infrastructure bundle; parallel with P1; about 3 days)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **D1 OS.0 spike** (no `src/`), recorded in `docs/object-storage-plan.md` | Pin `chrislusf/seaweedfs` by digest, with a namespace trust record. Confirm: `weed mini` env names; S3 port 8333; the filer's default **8888 (the owner's model port), never published**; master 9333; admin UI 12535 vs 23646; health endpoint; idle RSS; allow-all with an empty secret; botocore `when_required` checksums; pagination past 1,000 keys; non-ASCII keys; path vs virtual-host addressing | n/a | Spike | Findings recorded |
| **D2 OS.1 + OS.2 + A2 residue** | `docker-compose.yml` (profile `storage`, 1g, `./data/seaweedfs`, healthcheck, `depends_on required: false`, filer internal only; `MINIO_ROOT_*` at `:143-144` becomes `OBJECT_STORE_*`; MinIO comments at `:238,297,348` removed; **`OBJECT_STORE_REGION` (and later `OBJECT_STORE_PROVIDER`, `OBJECT_STORE_PREFIX`) added to `x-app-env` `:141-146`**); `.env.example:127-128,146-147` MinIO lines removed; `object_store.py:163-164` message says boto3 is missing from the image (no `s3` extra exists); `pyproject.toml:49` comment | `tests/test_compose_profiles.py` (seaweedfs only under `storage`; default services unchanged; no `MINIO_`; no host port 8888); `test_object_store_region_reaches_app_and_worker`; `test_missing_boto3_message_names_no_extra`; `test_env_example_names_no_minio` | Always on | A region set in `.env` reaches the code |
| **D3 OS.3** | `object_store.py` (timeouts, `when_required`, `max_pool_connections`, skip unchanged, circuit breaker in `archive_directory` at `:370`); `observability/metrics.py` (`object_store_archive_total{result}`, bytes) | `test_s3_config_has_timeouts_and_checksum_mode`; `test_archive_stops_after_first_error` | Always on | Metrics visible |
| **D4 OS.4** read-back | `server/runs.py:853,1326` call the existing `ensure_local` (`object_store.py:344`) and a `list_prefix` with a new `limit` | `test_download_falls_back_to_store_when_workspace_pruned`; `test_collect_artifacts_lists_store_when_workspace_gone`; `test_list_prefix_is_capped` | Always on | Download works after `workspaces --delete` |
| **D5** Readiness `storage` field (`ok / degraded / local-only / misconfigured`; never the value `error`, so never a 503) | `server/api.py:188` | `test_readiness_reports_storage_without_503`; `test_storage_field_never_uses_error_value` | Always on | Readiness stays 200 with the store down |
| **D6 OS.5** | `manage.py object-store backfill / verify / check` (check runs HeadBucket without printing secrets) | `test_manage_object_store_backfill_and_verify` | Always on | Backfill of existing runs verified |
| **D7 OS.6 + OS.7** | `tests/conftest.py` `s3` marker (runs when `OBJECT_STORE_TEST_ENDPOINT` is set); ADR-0012 (`docs/architecture-decisions.md:270`) Accepted; appendix row OS.7 (`docs/improvement-plan.md:3729`); HANDOVER steps for enable, rotate, back up (`rclone sync`), restore, roll back, and the IAM template, appended after §0 (the A11 marker makes ship-live independent of line numbers) | `s3` tests skip with a reason when no endpoint is set; `test_ship_live_finds_the_login_after_lines_are_inserted` stays green | Always on | HANDOVER steps exercised once |
| **D8 OS.10** Explicit provider and Amazon S3 | `object_store.py` (`OBJECT_STORE_PROVIDER`; `aws`: region required, `addressing_style auto`, no `create_bucket` (today at `:200`); `s3-compatible`: endpoint plus path style (today forced at `:177`); `OBJECT_STORE_PREFIX`); `.env.example` | `test_bucket_without_endpoint_needs_explicit_aws`; `test_aws_store_needs_region`; `test_aws_store_never_creates_bucket`; `test_s3_compatible_uses_path_style`; `test_prefix_applied_to_keys` | Always on | Store test against Amazon S3 if the owner provides a bucket |

- **OS.8** (rclone mirror, lifecycle expiry matching `run_retention`, a RustFS re-check around Q2 2027) stays optional. **OS.9** is dropped.
- **Acceptance:** the object-storage plan's criteria 1-6 (`docs/object-storage-plan.md:167-173`) on the live host. An unset bucket means Local, which is the rollback.

### Phase E: the service broker, tiers B/C/D for catalogued entries (after the owner's yes #3-7, 9 and 14; switch `SERVICES_REAL`; about 7 days)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **E1 spike** (half a day, no `src/`) | On Docker 29.8, verify: `--internal` has no egress; `network connect` of the live worker works and DNS aliases resolve; `OomScoreAdj` is honoured; the body Healthcheck with inspect polling works; socket permissions in a container; whether a create with `Binds` under `/home` would succeed; the canary results; that statvfs of the broker root reports VM disk free. Also: **evaluate a method-and-path regex proxy** against tecnativa and pin the chosen one; **measure Keycloak with a capped heap** (`-XX:MaxRAMPercentage`, `KC_CACHE=local`; class M if ≤768 MiB) | n/a | Spike | Findings recorded; proxy chosen |
| **E2** Spec builder and validator (built in dry-run, before any socket) | `src/app/services/spec.py` | `test_body_never_contains_forbidden_fields` (every entry, approved and learned); `test_memory_equals_swap`; `test_labels_present`; `test_no_free_form_args_path`; `test_device_requests_never_set`; `test_tmpfs_has_size_and_counts_in_lease` | Always on (code) | Dry-run bodies pass |
| **E3** Broker and proxy | `src/app/services/broker/{__main__,api,docker_api,reconcile}.py`; `docker-compose.yml` (`svc-proxy`, `svc-broker`, `svc-control` internal; worker `BROKER_URL`, `BROKER_TOKEN`, label `devflow.role=worker`; `git add -p`); `setup-env.sh` (`BROKER_TOKEN`); `tools/install_egress.py:45-46` `HARNESS_HOSTS` gains `svc-*`; `loop.sh deploy`, ship-live and `compose_up.sh` bring up the `services` profile; `model_ready.py` (broker state within a timeout; image and catalogue hash equal to the worker's) | `test_broker_ignores_caller_image_and_flags`; `test_broker_requires_token`; `test_broker_env_has_no_harness_secret`; `test_worker_connect_only_worker_label`; `test_inspect_mismatch_removes_container`; `test_every_docker_call_has_a_timeout`; `test_ready_returns_within_budget_when_broker_dead`; `test_ready_flags_broker_catalogue_hash_mismatch`; `test_deploy_brings_up_service_profiles`; `test_install_refuses_broker_hosts`; `test_compose_socket` (the worker socket is `/dev/null`; only `svc-proxy` mounts it; profile `services`; no ports) | `SERVICES_REAL` gates use | ALL READY with the broker up |
| **E4** Leases and gate | `src/app/services/leases.py` (the §3.9 formula; the worker reports its peak and current on `/renew`; leases rebuilt from labels; aggregate `NanoCpus` cap; free-disk floor) | `test_second_run_degrades_when_leases_exceed_vm`; `test_heavy_refused_when_max_heavy_zero`; `test_lease_clamped_to_class_max`; `test_oom_score_adj_set`; `test_aggregate_cpu_cap_degrades`; `test_pull_refused_below_free_disk_floor`; `test_leases_rebuilt_from_labels_after_broker_restart` | Always on (code) | Denials carry reasons |
| **E5** Readiness, init, reset, release, reaper, re-adoption | `reconcile.py`, `reaper.py` (containers **and** `devflow.run` networks; lease TTL for resumable endings); `_on_terminal`; rewind calls reset; worker re-attached on every worker start and resume | `test_readiness_timeout_drops_tier_not_ignored`; `test_reaper_selects_only_devflow_labels`; `test_reaper_prunes_devflow_networks`; `test_mismatched_hostconfig_on_resume_recreated`; `test_worker_reattached_after_recreate`; `test_rewind_resets_service_state`; `test_egress_canary_failure_disables_provider` | Always on (code) | A resume after a deploy re-attaches |
| **E6** Env injection and ledger | `sandbox.py` `_child_environment` gains `service_env_for`; `ledger.py`; `egress.py` adds per-uid rejects for other runs' subnets | `test_plan_env_reaches_product_commands_only_for_planned_runs`; `test_alone_hidden_mode_never_gets_service_env`; `test_broker_down_gives_provider_none_not_env_unavailable`; `test_absent_digest_steps_down_with_reason`; `test_run_uid_rejected_to_other_run_network` | `SERVICES_REAL` | Plan env present only for planned runs |
| **E7** Pre-pull, quota, scoring | `scripts/loop/loop.sh services prepull/up/down/status/selftest/learn` (a new subcommand); `scripts/loop/services_prepull.py` (the owner-named Docker Hub login; quota; LRU); `score.py` moves to `spec.py` | `test_prepull_only_catalogue_digests`; `test_quota_prunes_lru_never_system_prune`; `test_scoring_services_never_publish_owner_ports` (now through `spec.py`) | Tooling | Served scoring through the broker |
| **E8** Starter entries | Class S rows of §3.11, pinned with `resources.measured` from this host: postgres, valkey, mailpit, seaweedfs, ory-hydra, dex/mock-oauth2, nats, mosquitto, elasticmq, fake-gcs-server, lldap, mock-saml, temporal-dev, openbao, meilisearch. Class M (keycloak if E1 fits it, rabbitmq, azurite, moto, qdrant) only after measurement, at most one per run | Schema tests; one smoke per entry in `services selftest` | Data | Every S entry passes selftest |
| **E9** Two-instance check | `acceptance/suite.py` (two instances against the same plan env when a shared-state service is planned; generic) | `test_two_instance_check_flags_in_process_state` (fixture product); `test_two_instance_check_skipped_for_empty_plan` | Always on when a shared-state service is planned | The files-api reference passes it |

**`SERVICES_REAL`** stays on a switch until the owner rules on it (yes #15). For Learning runs it is on once deployed; for Measure it is an arm.

**Acceptance**
- Prerequisite: the owner's VM decision (#8).
- P2: files-api served ×2+2 and jobs-api ×2+2, switch on vs off.
- ALL READY throughout.
- Zero OOM kills of the owner's containers (`docker events`).
- Passively read model tokens/s and latency on :8888 and :1234 in their normal range.

**Deploy:** a full restart at a run boundary (new compose services), marked in STATE.

### Phase F: between-runs learning of uncatalogued open-source services (switch `SERVICES_USE_LEARNED`, off; about 3 days)

| Item | Files | Tests (recorded fixtures, no network) | Mode | Acceptance |
|---|---|---|---|---|
| **F1** Discovery, trust, SSRF guard | `src/app/services/discovery.py` | `test_typosquat_t3_is_review_needed_never_started`; `test_ref_not_in_fetched_docs_rejected`; `test_redirect_off_allowlist_refused`; `test_private_ip_resolution_refused` | Learner (operator command) | Fixtures pass |
| **F2** Per-version licence for learned entries | Extends `licence.py` | `test_two_sources_must_agree`; `test_extra_readme_terms_review_needed` | Learner | Fixtures pass |
| **F3** Pinning and size | `src/app/services/pinning.py` | `test_tag_at_least_14_days_never_latest`; `test_moved_digest_review_needed`; `test_oversize_image_not_auto_pulled` | Learner | Fixtures pass |
| **F4** Contract learning, smoke, learner command | `src/app/services/{contract_learn,smoke}.py` (schema-only prompt, no tools); `loop.sh services learn` (nightly from `requests.jsonl`; `IMAGES` open only while it runs) | `test_uncited_env_dropped`; `test_socket_in_docs_triggers_review`; `test_cap_probe_stops_at_minimal_set`; `test_one_smoke_host_wide`; `test_learner_never_runs_during_a_measure_batch_or_a_live_run`; `test_learned_file_written_status_learned`; ban test | Learner | One request learned end to end |
| **F5** Snapshot pinning and quarantine | `resolver.py`; `scripts/loop/kpi_ledger.py` (catalogue hash column) | `test_measure_run_uses_pinned_snapshot`; `test_entry_learned_mid_batch_quarantined` | Always on (code) | Hash recorded per run |
| **F6** Admin review page and use switch | `/admin` learned entries (approve, block, edit); `SERVICES_USE_LEARNED` module and registration | `test_learned_entry_rendering_escaped`; `test_owner_edit_wins_over_relearn`; `test_learned_entry_unused_when_switch_off` | `SERVICES_USE_LEARNED` | P3 |

**Acceptance (P3):** a jobs-api variant names an OSI service whose entry has been removed (for example Temporal). The learner learns it between runs; two runs with `SERVICES_USE_LEARNED` on and two off are provisioned and scored.

### Phase G: licence class opt-in (plumbing always on; acceptance only through the owner's settings action; about 1 day)

| Item | Files | Tests (fail on old code) | Mode | Acceptance |
|---|---|---|---|---|
| **G1** Class records and Licences page | `src/app/services/licence_records.py`; a settings "Licences" page that shows the terms link and edition limits first; `acceptance_env` applied only with a record | `test_acceptance_env_absent_without_record`; `test_record_not_creatable_by_api_token_or_model_path`; `test_class_opt_in_covers_all_entries_of_that_class`; `test_major_change_requires_new_acceptance` | Always on | With the SSPL opt-in, a MongoDB brief plans tier B (class M, gate permitting) |

Vendor-entry tier B (HANA, Oracle, SQL Server, Db2) is filed in Phase I.

### Phase I: filed (not built here)

- **A per-run product runner container** (`PRODUCT_RUNNER_CONTAINER`, registered only when built, after E):
  - the broker starts one long-lived container per run, from the worker image, on the run network only, under the run's uid;
  - installs go through the A12 proxy, and commands through a typed exec channel owned by the broker;
  - the worker leaves the run networks;
  - it is measured, because it changes timings.
- **E10, building the product image through the broker**, behind a switch and measured:
  - `BUILD` is enabled only for the broker, with no host entitlements and a disk quota;
  - compose up from the product's own compose is mapped onto broker specs.
- **Validation tiers 2-3** (`act`, `compose up --wait`, kind, `helm install`). Only on a separate rootless engine or VM, with no egress, actions cached offline and Pod Security `restricted`. Never the owner's Desktop VM.
- **Containerised scoring**, so hermetic BYO runs can be scored and products never run on the owner's host.
- **A rootless engine on the owner's host** (Podman), if the owner says yes (#14).
- **Intake-time learning**, once the between-runs learner is measured.
- **Vendor-entry tier B** (G2), once the VM has 12 GiB or more: per-entry and major-version opt-ins; `heavy` and `arch` gates; `IPC_LOCK`/`IPC_OWNER`/`Sysctls` for licensed heavy entries only.
- **The E0 process runner** (real binaries as worker children), only if the owner defers the socket yes for a long time. It needs a per-service memory limit first.
- **Sysbox or gVisor**, if Docker Desktop on Linux accepts one (u).

**Effort total:** about 39 working days (u).

---

## 6. Measurement

**Families**

| Family | Role | Services in hidden tests |
|---|---|---|
| tasks-api, notes-api-hono | Sentinels: empty plan, no regression; re-baselined after A7 and after B | None |
| files-api | Alone (tier 0, diagnosis) and served (real or BYO) | Alone: none. Served: plan env |
| jobs-api | Served mode plus artifact checks | Plan env via `score.py` |
| jobs-api uncatalogued variant | Phase F | Plan env |
| BYO runs (owner's S3, self-hosted S3) | Mechanics only, `non_comparable` | Not scored by `score.py` |

**MF.4 pairs**
- A Measure run is one frozen harness SHA, plus the catalogue snapshot hash, plus the pre-pulled digests, with no deploy inside it.
- Two runs per family per arm.
- A mixed-version run counts for neither arm.
- Runs with different tiers, snapshots, or sides of the A7 or B SHAs are never compared.
- Arms run on one SHA with `SWITCHES_OFF/ON` (`loop.sh:151-155`) and are compared with `kpi_ledger.py switch-arms` (`:220`).

| Pair | When | Arms | Expected |
|---|---|---|---|
| P0 | Before A7 and B | files-api ×2, tasks-api ×2, notes-api-hono ×2 | Baseline: alone; served with env ignored |
| P0b | After A7 | Sentinels ×2 each | New sentinel baseline; no hidden fall |
| P1 | After B+C+V | files-api ×2, jobs-api ×2 (tier E), sentinels ×2 | Alone up; a tier-E baseline for served; sentinels re-baselined |
| P2 | After E | `SERVICES_REAL` on/off: files-api 2+2, jobs-api 2+2 | Served up with on; alone unchanged |
| P3 | After F | `SERVICES_USE_LEARNED` on/off on the variant, 2+2 | Served up with on |
| P4 | After V | `ARTIFACT_FINDINGS_AS_DEFECTS` on/off on jobs-api, 2+2 | Artifact checks up; no hidden fall |
| P5 | After E | `SERVICES_SUBSTITUTES` on/off on files-api, 2+2 | Served up, or a recorded fidelity gap |

**KPIs** (`loop.sh kpi`, `data/kpi/ledger.csv`)
- **Product and pipeline:**
  - hidden score per mode (`alone`, `served`, `artifacts`) and the quality score; neither may fall on any family;
  - boot-alone rate, `start_failure_named`, and two-instance check results;
  - services quoted, resolved and invented (invented must be 0);
  - tier per service, and step-down reasons;
  - provisioning minutes, readiness failures, leases denied, and the `environment-unavailable` count;
  - release gaps; validator verdicts per tier, plus defects and fix rounds;
  - false acceptances; secrets in transcripts (must be 0);
  - the catalogue snapshot hash.
- **Owner protection:**
  - ALL READY at every audit during provisioning;
  - peak VM MemAvailable and VM free disk;
  - OOM kills in the owner's containers (must be 0);
  - the worker's `memory.peak`;
  - the summed service `NanoCpus`;
  - model tokens/s and latency on :8888 and :1234, read passively from harness model-call telemetry against an idle baseline, never by probe requests;
  - no host port collisions.

**Verdicts** follow `docs/measuring.md`:
- **Kept:** no hidden or quality score falls, and the target KPI moves.
- **Parked:** nothing moves.
- **Removed:** it hurts.

**Register** (with the full four-part registration): `SERVICES_REAL`, `SERVICES_USE_LEARNED`, `SERVICES_SUBSTITUTES` and `ARTIFACT_FINDINGS_AS_DEFECTS`. `PRODUCT_RUNNER_CONTAINER` is registered only when it is built.

**Fallback MF.4 exception (owner decision).** If served-mode scores are ruled out of scope, keep `SERVICES_REAL` when no hidden or quality score falls and the jobs-api served or production-path KPIs move. Provisioning is a requirement the owner set, not a score lever.

---

## 7. Risks, open questions and the owner's explicit yes

### Risks

**Security and isolation**
- **The proxy filters paths, not bodies,** and with tecnativa it reaches every container on the engine. The broker code is the boundary. Controls:
  - the typed builder and validate-then-inspect;
  - an env with no secrets;
  - the token, plus A7 and A8;
  - the label reaper;
  - the E1 proxy choice;
  - Phase I.

  Residual risk: a broker bug creating binds into Desktop-shared host paths (checked in E1), or touching the owner's other containers.
- **Cross-run reach.** The worker sits on both run networks. Per-run passwords, per-run uids and the per-uid subnet rejects (E6) bound this. Loopback inside the worker is shared, so two runs' product servers can still reach each other on 127.0.0.1.
- **Product reach to the host.** Until A8 lands, product code can reach the owner's :1234 (no key). A8 is the highest-value safety item after A7 and A9.
- **The live floor depends on the sidecar.** If `net-floor` is not re-run after a worker recreate, the floor is absent. The deploy steps re-run it, `ready` probes it live, and product commands wait for it and then pause the run.
- **Real BYO credentials reach model-written code.** Mitigated by scoped credentials, redaction, the proxied allowlist (A12) and a statement in the UI. SDKs or DB drivers that ignore proxy env, and TLS hostname checks over loopback forwarders, are (u) until Phase C.
- **AGPL services** (Grafana, Loki, Garage, Zitadel, Redis 8 for the harness) run as separate network services, and the release note says the product does not link them.

**Measurement and fidelity**
- **Substitute fidelity.** SQLite vs Postgres SQL, FerretDB error codes, Dex/Hydra/mock-oauth2 vs Keycloak claims, lenient fakesnow, and an incomplete BigQuery emulator. These are recorded as `substituted` or `emulated` and never compared with tiers A and B.
- **Learning drift.** Handled by snapshot pinning and quarantine. Licence labels can be wrong, so two sources must agree, the watch list applies, and a moved digest gives `review-needed`.
- **Timing shifts.** A7, A8, A12, B3 and B8 change timings for every family. Hence P0b, P1 and the sentinel re-baselines.

**Resources**
- **4 GiB VM.** About 1.8 GiB is available and worker peaks reach 1.5-4 GiB, so realistically only class S fits, often for one run at a time. Expect frequent gate denials until the VM is raised. The worker's `8g` limit is larger than the VM (noted; not changed here).
- **CPU.** Service CPU competes with the llama-servers' host threads. The aggregate cap starts at 2 CPUs.
- **tmpfs data counts against the memory cgroup.** Every tmpfs has a `size=`, and the lease includes it.
- **Disk.** Heavy images are 1.5-3 GB each. The quota and the free-disk floor apply, and leaked networks are pruned by the reaper.
- **Rate limits.** Docker Hub unauthenticated pulls (about 10/h, (u)) and the GitHub API (60/h) are covered by host pre-pull, the owner-named login, a token, a 24 h cache and an optional pull-through cache.

**Operations**
- **A3 changes every Redis consumer together.** The Redis 8 load of a 7.4 AOF is (u); `ready` fails closed, and `deploy --with-redis` sequences the restart.
- **A7 changes ownership and process control.** The spike covers workspaces, caches, Playwright, git and cleanups. Then a one-off regroup and three sentinels.
- **Docker Desktop hangs.** Every broker call has a timeout, `ready` never hangs, and restarting Docker Desktop follows the standing permission (pause runs first).
- **Supply chain.**
  - Validator binaries are sha256-verified.
  - Validators run with no network.
  - Image provenance and SBOM attestations are recorded where published.
  - Curated namespaces need owner trust records.
- **Prompt growth.** The services paragraph is generated, absent for an empty plan, and limited to names, tier and fallback.
- **The owner's compose hunk** stays uncommitted through A3, A8, A11, D2, C3, E3 and every switch line. `git add -p` and the A11 guard protect it.

### Open questions (each answered by the named spike or ruling, not assumed)

1. **Catalogue location (owner ruling before B1).** Is `src/app/stacks/services/` (machine data, a "service pack") an acceptable reading of AGENTS.md, with model-facing wording in `seed.py`? This includes the category fallback text rendered into the contract from `_categories.toml`, and `INSTALL_HOSTS` in packs.
2. **Do files-api and jobs-api join the Measure families**, and does either join the gate?
3. **SeaweedFS (D1):** env names, health endpoint, admin port, idle RSS, empty-secret behaviour, addressing.
4. **Docker 29.8 (E1):**
   - `network connect` to an internal network;
   - socket permissions;
   - binds under `/home`;
   - statvfs of the VM disk;
   - the proxy choice (tecnativa vs regex);
   - Keycloak with a capped heap.
5. **A7 spike:** file caps on Desktop overlayfs, cache ownership, Playwright relocation, git `safe.directory`, deleting tarball-extracted directories.
6. **A8 spike:** `xt_owner`, iptables-nft vs legacy, IPv6, the host gateway, host-loopback reach.
7. **A3:** does Redis 8 load the current 7.4 AOF, or is a flush needed?
8. **A12:** which product SDKs and drivers honour proxy env, and does TLS work through loopback forwarders?
9. **Sysbox or gVisor** on Docker Desktop for Linux (u). This decides parts of Phase I and tiers 2-3.
10. **Measured RAM and start time for every starter entry** (all are (u) today).
11. **Release naming:** should `.env.example` and the README name the production service, the category, or both? Proposed: both, plus the tier used in testing.

### What needs the owner's explicit yes

| # | Decision | Needed for | Recommendation |
|---|---|---|---|
| 1 | A3 rollout: regenerate `.env`, change the Redis image to a digest-pinned Redis 8 (AGPL) or Valkey, and restart redis, app and worker at a boundary | A3 | Yes (Redis 8) |
| 2 | A one-shot `net-floor` sidecar with `NET_ADMIN` in the worker's network namespace (the worker gains no capability) | A8, A12 | Yes |
| 3 | E1 spike: throwaway containers (including Keycloak), and connecting the live worker to a test network between runs | E1 | Yes |
| 4 | Docker socket in `svc-proxy`, and a broker on the Desktop engine that can reach every container on it (this reverses the masked socket and K.2) | Phase E | Yes, after A7 and A8, with the §4 controls |
| 5 | The broker connects the worker to per-run networks | Phase E | Yes; removed in Phase I |
| 6 | Image pulls with a 15 GB quota and nightly pre-pull; compose profiles `storage`, `services` and `floor`; **which Docker Hub login pre-pull uses** (the harness operator account is not a Docker Hub credential); served scoring with the pinned compose | B0 served mode, D, E | Yes; the owner names the login |
| 7 | Discovery egress, a fine-grained no-scope GitHub token, and `IMAGES` open while `services learn` runs | Phase F | Yes; T1/T2 and owner-trusted namespaces only |
| 8 | Docker Desktop VM memory: keep 4 GiB (class S only; the services in §1.8 stay at A/D/E) or raise to 8 GiB; heavy entries need 12-16 GiB or more. **This decision gates Phase E** | E; class M/H; two runs with services | 8 GiB, the owner's call; the harness never changes it |
| 9 | Namespace trust records for curated images outside T1/T2 (gvenzl, chrislusf, navikt, tecnativa or the chosen proxy, axllent, and others as listed) | B1, E8 | Yes, entry by entry |
| 10 | Licence class opt-ins (SSPL, RSAL, BUSL, Redpanda BSL and the like) and the non-OSI list (n8n, Vault, Nomad, Directus, Restate, Inngest, Dragonfly, Redis 7.4-7.8, the Drone image) | Phase G | Only through the owner's settings action |
| 11 | BYO Connections with real, scoped credentials (Amazon S3, Azure, GCS, Atlas, HANA Cloud, an IdP); any cloud cost is the owner's | Phase C use | Scoped credentials only |
| 12 | files-api and jobs-api as Measure families; gate membership | B0 | Yes as Measure families; gate later |
| 13 | The fallback MF.4 exception in §6 | E, F | Only if served mode is ruled out |
| 14 | A rootless engine (Podman) on the owner's host as a later alternative for class M/H and tiers 2-3 | Phase I | Decide after the VM decision |
| 15 | Whether `SERVICES_REAL` is a quality change (always on, per the 2026-11-05 switch policy) or stays a measured switch | E | Keep as a switch until P2 |
| 16 | The AGENTS.md reading of the service pack (open question 1) | B1 | Yes |

---

## 8. Sources (retrieved 2026-11-10)

### Verified by the harness comparison pass

- OpenAI Codex:
  - https://learn.chatgpt.com/docs/environments/cloud-environments.md
  - https://learn.chatgpt.com/codex/environments/modes
  - https://learn.chatgpt.com/docs/environments/cloud-environment
  - https://learn.chatgpt.com/docs/cloud/internet-access
  - https://learn.chatgpt.com/docs/changelog
  - https://github.com/openai/codex-universal
- GitHub Copilot:
  - https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment
  - https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-firewall
  - https://docs.github.com/en/copilot/concepts/agents/coding-agent/risks-and-mitigations
  - https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers
  - https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers
  - https://github.blog/changelog/2025-07-30-copilot-coding-agent-custom-setup-steps-are-more-reliable-and-easier-to-debug
  - https://github.blog/changelog/2026-03-13-optionally-skip-approval-for-copilot-coding-agent-actions-workflows/
  - https://github.blog/changelog/2026-10-28-work-from-anywhere-with-a-new-connected-copilot-cloud-experience/ (the cloud sandbox default supports no setup steps or services)
- Devin:
  - https://docs.devin.ai/onboard-devin/environment.md
  - https://docs.devin.ai/onboard-devin/environment/blueprints.md
  - https://docs.devin.ai/onboard-devin/environment/blueprint-reference.md
  - https://docs.devin.ai/onboard-devin/environment/scenarios.md
  - https://docs.devin.ai/work-with-devin/testing-and-recordings.md
  - https://docs.devin.ai/product-guides/security-profiles.md
  - https://docs.devin.ai/enterprise/deployment/devin-connect.md
  - https://docs.devin.ai/release-notes/2026.md
- Google Jules:
  - https://jules.google/docs/environment/ (Docker 28.2.2 and Compose v2.36.2 in the base image; MCP partners)
  - https://jules.google/docs/changelog/2026-02-19
  - https://jules.google/docs/changelog/2026-10-29 (read-only from 2026-11-11, closes 2026-12-31)
- OpenHands:
  - https://docs.openhands.dev/openhands/usage/sandboxes/overview
  - https://docs.openhands.dev/openhands/usage/sandboxes/docker
  - https://docs.openhands.dev/enterprise/docker-in-sandbox
  - https://docs.openhands.dev/enterprise/k8s-install/sysbox
  - https://docs.openhands.dev/enterprise/k8s-install/resource-limits
  - https://docs.openhands.dev/sdk/guides/secrets
  - https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-workspace/openhands/workspace/docker/workspace.py
- SWE-agent and SWE-ReX:
  - https://github.com/SWE-agent/SWE-agent
  - https://github.com/SWE-agent/SWE-ReX/blob/main/src/swerex/deployment/docker.py
- Cursor (verified parts only):
  - https://cursor.com/docs/cloud-agent/builds
  - https://cursor.com/docs/cloud-agent/setup

### Unverified (u): to be checked at pin or build time

Every catalogue version number, image size and RSS figure in §3.11 is unverified, as are the class assignments that depend on them.

- **Services and licences:**
  - https://redis.io/legal/licenses/
  - https://www.infoq.com/news/2025/05/redis-agpl-license
  - https://hub.docker.com/r/valkey/valkey
  - https://hub.docker.com/_/rabbitmq
  - docs.cockroachlabs.com/docs/stable/licensing-faqs
  - docs.nats.io/reference/config/jetstream/max_memory_store
  - keycloak.org/server/containers
  - https://docs.temporal.io/cli/server
  - https://hub.docker.com/r/temporalio/auto-setup
  - https://github.com/netresearch/ofelia
  - https://hashicorp.com/blog/hashicorp-adopts-business-source-license
  - https://github.com/hashicorp/vault/blob/main/LICENSE
  - https://github.com/openbao/openbao/blob/main/LICENSE
  - https://openbao.org/docs/concepts/dev-server/
  - https://www.getunleash.io/blog/unleash-moving-to-agplv3
  - https://raw.githubusercontent.com/restatedev/restate/main/LICENSE
  - https://raw.githubusercontent.com/harness/harness/drone/LICENSE
  - https://raw.githubusercontent.com/getsops/sops/main/LICENSE
  - The Elasticsearch AGPL option since 8.16: to be checked against the Elastic licence page.
- **Jobs and workflows:**
  - https://docs.celeryq.dev/en/stable/userguide/monitoring.html
  - https://docs.celeryq.dev/en/stable/reference/cli.html
  - https://pypi.org/project/celery/
  - https://python-rq.org/docs/workers/
  - https://www.npmjs.com/package/bullmq
  - https://www.npmjs.com/package/pg-boss
  - https://www.prefect.io/docs/v3/how-to-guides/self-hosted/server-docker
- **CI/CD, Kubernetes and validators:**
  - https://docs.docker.com/compose/how-tos/profiles/
  - https://docs.docker.com/reference/cli/docker/compose/config/
  - https://kind.sigs.k8s.io/docs/user/quick-start/
  - https://helm.sh/docs/helm/helm_lint/
  - https://www.cncf.io/announcements/2025/11/12/helm-marks-10-years-with-release-of-version-4/
  - https://github.com/rhysd/actionlint
  - https://github.com/yannh/kubeconform
  - https://github.com/stackrox/kube-linter
  - https://nektosact.com/usage/index.html
  - https://woodpecker-ci.org/docs/usage/linter
  - https://woodpecker-ci.org/docs/usage/local-execution
  - https://tekton.dev/docs/pipelines/install/
  - https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/
  - https://opentelemetry.io/docs/collector/configuration/
  - https://www.jaegertracing.io/docs/2.23/getting-started/
  - https://www.envoyproxy.io/docs/envoy/latest/operations/cli
  - https://www.haproxy.com/blog/announcing-haproxy-3-2
- **Object storage:**
  - https://github.com/seaweedfs/seaweedfs
  - https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini
  - https://github.com/seaweedfs/seaweedfs/wiki/Amazon-S3-API
  - https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/
  - https://advisories.gitlab.com/cargo/rustfs/CVE-2025-68926/
  - https://linuxiac.com/rustfs-1-0-s3-compatible-object-storage-reaches-ga/
  - MinIO's archival rests on a secondary source (https://glukhov.org/data-infrastructure/object-storage/minio-dead/); to be checked against the primary repo, https://github.com/minio/minio.
- **Socket proxies:** `tecnativa/docker-socket-proxy` scope and `wollomatic/socket-proxy`, to be checked in E1.

### Repo evidence (verified)

- The file:line references in §2, checked against HEAD `e6cf8a95` plus the working copy.
- Commits `47190e23` (LF.782), `a9f858ce` (LF.783), `c5d22b1d` (LF.784, LF.785) and `98eb0981` (LF.786).
- The `/proc` environ readability probe (no values printed).
- Host and VM figures measured read-only on 2026-11-10.

---

## Changes not taken

- **Critic 12, `user: "0"` on the worker, dropping `NET_ADMIN` before appuser.** Not taken. A one-shot `net-floor` sidecar in the worker's network namespace keeps the worker as appuser, so `loop.sh`, deploy and hold files stay appuser-owned, and the worker never holds NET_ADMIN.
- **Critic 12, an allowlist egress mode switched per run through dynamic rules.** Taken as a static proxied uid pool plus a loopback proxy instead. Only the one-shot sidecar holds NET_ADMIN, so rules cannot change per run.
- **Critic 9, Helm values generated for every product.** Taken only when the product ships a chart; without a chart, generated values feed nothing.
- **Critic 4, measuring Keycloak in D1.** Moved to E1, because D1 is a SeaweedFS-only spike, and throwaway containers are approved under yes #3.
- **Critic 6, "make the VM decision a gating dependency".** Taken as "the owner's keep-or-raise decision gates E", not "a raise is required", because class S at 4 GiB still delivers served-mode value.
- **Critic 8, a two-instance check on every run.** Applied only when a shared-state service is planned. With an empty plan, two instances on separate `DATA_DIR`s test nothing about scaling.
- **Critic 3, the Service Bus emulator as a starter entry.** Added as data only, class H, because it needs a SQL Server container (u).
- **Critic 7, OpenTofu, tflint and ansible-lint versus the count rule.** Built as V6 without waiting for V0 counts, as the critic required. Only the six non-core validators are count-gated (V7).
- **Draft's per-substitute `SVC_SUB_*` switches.** Replaced by one group switch, `SERVICES_SUBSTITUTES`, plus per-entry data, because the registry lists each switch by name.
- **Draft's `SERVICES_AUTO_RESOLVE` switch.** Removed, because learning moved out of the run path into an operator command. `SERVICES_USE_LEARNED` is the only run-path switch.
- **Critic 20, ship A3 and A7 together.** Taken as one boundary deploy when A7's spike passes. Otherwise A3 ships alone, labelled defence in depth, rather than holding a pinned, licence-clean Redis behind A7.