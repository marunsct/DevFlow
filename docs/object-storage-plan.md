# Object storage for DevFlow: replacing MinIO with SeaweedFS

*2026-10-20 · status: PLAN (no code changed) · plan items OS.0–OS.8: [improvement-plan.md Appendix 6](improvement-plan.md#plan-os) · research: [research-findings.md R8](research-findings.md#r8) · decision: ADR-0012 (proposed)*

## 1. Decision

**Use SeaweedFS (Apache-2.0) in single-process `weed mini` mode, as an opt-in compose profile.**
Runner-up: RustFS. Not chosen: Garage, Ceph RGW, MinIO AIStor Free.

Priority: **P2.** It protects run output and enables multi-node workers; it does not change
build quality or local-model speed, so it should not displace P0/P1 harness items.

## 2. Why MinIO has to go

| Date | Event |
|---|---|
| May 2025 | Admin console removed from the community edition |
| Oct 2025 | Community Docker images and public binaries stopped (source-only) |
| Dec 2025 | Maintenance mode announced |
| Feb / Apr 2026 | GitHub repo archived (read-only); last push 24 Apr 2026 |
| Oct 2026 | Vendor's free tier ("AIStor Free") is commercial, not open source, and single-node only |

An archived, source-only server with no security fixes is not something to add to a stack now.

## 3. Candidates compared

| | **SeaweedFS** | RustFS | Garage | Ceph RGW |
|---|---|---|---|---|
| License | Apache-2.0 | Apache-2.0 | AGPL-3.0 | LGPL |
| Age / maturity | Since 2015, ~34k stars, release 4.45 on 2026-08-31 | Source opened Jul 2025; **1.0 GA 16 Sep 2026** | Since 2020, small team | Very mature |
| Single-host setup | One command (`weed mini`), creds + bucket from env | One container, MinIO-like console | Config file + RPC secret + layout assign/apply + key/bucket via CLI | Disproportionate for one host |
| S3 coverage DevFlow could grow into | Versioning, object lock, bucket policy, CORS, presigned, multipart, lifecycle (no transitions) | Broad (claims near-full) | No versioning, no object lock, no bucket policies; lifecycle partial | Broad |
| Security track record | No critical advisories found in this research | **CVE-2025-68926** (hard-coded gRPC token, CVSS 9.8), **CVE-2026-62378** (console stored XSS leaking keys, CVSS 9.0, Jul 2026) and others | Clean in this research | Mature process |
| Small-file workloads | Its design strength (archived workspaces are thousands of small source files) | Good | Good | Good, heavy |

**Why SeaweedFS:** it is the only option that is permissively licensed, a decade old, actively
releasing, and a one-command single-node deployment. Its project docs explicitly position
`weed mini` for "many single-node and small-cluster production setups". It handles many small
objects well, which is exactly what `archive_directory` produces.

**Why not RustFS (yet):** closest to MinIO's UX and Apache-2.0, but GA is five weeks old and
it had two critical-severity advisories in the past ten months. Re-evaluate at 1.x + six months.
Because DevFlow speaks plain S3 through boto3, switching later is a config change.

**Why not Garage:** AGPL, no versioning/object lock, and its bootstrap (layout, keys via CLI,
bucket-create permission per key) adds steps the existing `_ensure_bucket()` path would trip on.

## 4. Is it worth having? Honest assessment

What DevFlow does today (verified in the code):

- `object_store.py` is a clean abstraction with a Local and an S3 backend, plus tests.
- Uploads are archived on receipt and fetched back with `ensure_local` (`runs.py`).
- Run workspaces are archived once at a terminal stage (`runner._archive_artifacts`).
- Run deletion removes stored copies (`run_retention.py`).
- **But** the MinIO service is commented out, so the Local backend is in use and writes to
  `DATA_DIR/objects` — **on the same `appdata` volume** as the workspaces. The "second copy"
  dies with the first.
- **And** artifacts are write-only: `download_artifact` reads only the workspace; nothing reads
  `runs/<id>/…` back.

Advantages it would bring:

1. **Real durability** – copies on a separate bind mount (`./data/seaweedfs`, ideally another
   disk), surviving `docker compose down -v`, a corrupted volume, or a workspace wipe. Mirrors
   the move already made for Postgres to `./data/postgres`.
2. **Off-site backup for free** – any S3 tool (`rclone`, `aws s3 sync`) can mirror the bucket
   to cloud storage or a NAS; no DevFlow code needed.
3. **Multi-node workers** – the documented reason the abstraction exists: a worker on another
   machine can read uploads and the API can serve artifacts it didn't write.
4. **Downloads after cleanup** – finished runs' workspaces can be pruned to save disk while the
   produced files remain downloadable.
5. **Inspectability** – browse runs' outputs in SeaweedFS's admin UI or any S3 browser.
6. **Future options** – presigned download URLs (offload large files from the API), lifecycle
   expiry aligned with run retention, versioning for review documents.

Costs: one more container (give it a 1 GB limit like the other services), ~2× disk for
archived output, and a credential to manage. On a single machine with no backup plan the
gain is modest — **the value comes from #1 + #2 together**, or from adding a second worker.

## 5. Implementation plan

Every step keeps `OBJECT_STORE_BUCKET` unset ⇒ Local backend as the rollback path.

### OS.0 Spike — confirm compatibility (½ day)
- Run `chrislusf/seaweedfs:<pinned>` with `weed mini -dir=/data`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET=devflow-artifacts`.
- Run the existing `tests/test_object_store.py` cases against the S3 backend (see OS.6).
- Check the four risk points: boto3 1.43's default request checksums (set
  `request_checksum_calculation="when_required"` if uploads fail), `head_bucket`/`create_bucket`
  semantics, `list_objects_v2` pagination past 1,000 keys, non-ASCII and space-containing keys.
- Confirm the health endpoint to use in compose (master `:9333/cluster/healthz` or the S3 port).
- **Exit:** all store tests green against SeaweedFS; findings added to research Part R8.

### OS.1 Compose service (opt-in profile)
```yaml
  seaweedfs:
    image: chrislusf/seaweedfs:4.45          # pin what OS.0 tested
    profiles: ["storage"]
    restart: unless-stopped
    command: ["mini", "-dir=/data"]
    environment:
      AWS_ACCESS_KEY_ID: "${OBJECT_STORE_ACCESS_KEY:-devflow}"
      AWS_SECRET_ACCESS_KEY: "${OBJECT_STORE_SECRET_KEY:-}"
      S3_BUCKET: "${OBJECT_STORE_BUCKET:-devflow-artifacts}"
    expose: ["8333"]
    ports:
      - "127.0.0.1:${SEAWEED_ADMIN_PORT:-23646}:23646"   # admin UI, loopback only
    volumes:
      - ./data/seaweedfs:/data                # bind mount, outside `down -v`
    healthcheck: { … endpoint confirmed in OS.0 … }
    deploy: { resources: { limits: { cpus: "1", memory: 1g } } }
```
- `app`/`worker` `depends_on` it with `required: false` so the default stack still starts.
- **Fail closed:** an empty secret puts SeaweedFS in allow-all mode, so the app refuses to use
  an S3 endpoint with an empty `OBJECT_STORE_SECRET_KEY` (see OS.3), and `setup-env.sh` always
  generates one.

### OS.2 Configuration rename
- `.env.example`, `setup-env.sh`, `docker-compose.yml`: replace `MINIO_ROOT_USER/PASSWORD`,
  `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` with `OBJECT_STORE_ACCESS_KEY/SECRET_KEY` and
  `SEAWEED_ADMIN_PORT`; endpoint `http://seaweedfs:8333`; bucket `devflow-artifacts`.
- Keep reading the old `MINIO_*` names for one release with a deprecation log line.
- Remove the commented `minio` blocks and `miniodata` volume; update the pyproject comment.

### OS.3 Harden `object_store.py`
- Client config: checksum mode from OS.0, connect/read timeouts, `max_pool_connections` ≥
  `HARNESS_MAX_PARALLEL`.
- Refuse an S3 endpoint with empty credentials (`ObjectStoreError`, logged at start).
- Readiness: `server_health` reports object storage as `ok / degraded / local-only`, so a
  silent fallback to "nothing archived" is visible on the health page.
- Metrics: `object_store_archive_total{result}` and bytes, via the existing multiprocess
  Prometheus registry.
- Skip re-uploading unchanged files (size + mtime/etag) so re-archiving a resumed run is cheap.

### OS.4 Read-back path (the missing half)
- `download_artifact`: if the workspace file is absent, `ensure_local("runs/<id>/<path>")`
  into a temp path and serve it; audit as today.
- Artifact listing for a run whose workspace was pruned comes from `list_prefix("runs/<id>")`.
- Optional follow-up: presigned URLs for files over a size threshold.

### OS.5 Backfill and migration
- `manage.py object-store backfill [--run ID]`: archives existing workspaces/uploads missing
  from the store (`iter_missing` already exists).
- One-time import of anything in `DATA_DIR/objects` from the Local backend.
- `manage.py object-store verify`: counts missing keys per run.

### OS.6 Tests
- Parametrise the existing store tests over both backends; the S3 variant is marked
  (`@pytest.mark.s3`) and runs when `OBJECT_STORE_TEST_ENDPOINT` is set.
- New: download falls back to the store when the workspace file is gone; empty-secret refusal;
  health reports `degraded` when the endpoint is down; archiving still never fails a run
  (existing outage tests keep passing).
- Each new test is proven to fail on the old code, per the repo's convention.

### OS.7 Docs (repo convention: one file per topic)
- Done with this plan (2026-10-20): ADR-0012 (Proposed) in `architecture-decisions.md`, Part R8 in
  `research-findings.md`, Appendix 6 and Appendix M rows in `improvement-plan.md`.
- At implementation: set ADR-0012 to Accepted, and add to `HANDOVER.md`: enable (`docker compose --profile storage up -d`), rotate keys, back up
  (`rclone sync`), restore, roll back (unset `OBJECT_STORE_BUCKET`).

### OS.8 Optional follow-ups
- Off-site mirror as a scheduled `rclone` job.
- Bucket lifecycle expiry matching `run_retention`, so deletes are enforced on both sides.
- Re-evaluate RustFS in ~Q2 2027.

### Acceptance criteria
1. `docker compose --profile storage up` starts healthy; default `up` without the profile is unchanged.
2. A completed run's files appear under `runs/<id>/` in the bucket; uploads under `uploads/`.
3. Deleting the run's workspace, its files still download from the run page.
4. Deleting a run removes its objects.
5. Stopping SeaweedFS mid-run: the run completes, health shows `degraded`, backfill catches up.
6. `docker compose down -v` leaves `./data/seaweedfs` intact.

### Effort
About 2–3 days: OS.0 ½, OS.1–OS.2 ½, OS.3 ½–1, OS.4 ½, OS.5–OS.6 ½, OS.7 ¼.

## Sources
- MinIO CE timeline: [glukhov.org – MinIO CE in 2026](https://glukhov.org/data-infrastructure/object-storage/minio-dead/), [WZ-IT – MinIO is archived (updated 12 Oct 2026)](https://wz-it.com/en/blog/minio-successor-s3-storage-comparison/)
- SeaweedFS: [repo](https://github.com/seaweedfs/seaweedfs), [releases](https://github.com/seaweedfs/seaweedfs/releases), [weed mini quick start](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini), [S3 API coverage](https://github.com/seaweedfs/seaweedfs/wiki/Amazon-S3-API)
- RustFS: [1.0 GA (Linuxiac, 19 Sep 2026)](https://linuxiac.com/rustfs-1-0-s3-compatible-object-storage-reaches-ga/), [CVE-2025-68926](https://advisories.gitlab.com/cargo/rustfs/CVE-2025-68926/), [CVE-2026-62378](https://cve.halosecurity.com/cve-advisory/cve-2026-62378-rustfs-console-stored-xss-exposes-credentials)
- Garage: [S3 compatibility reference](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)
- Comparison: [Elestio – RustFS vs SeaweedFS vs Garage (Apr 2026)](https://blog.elest.io/rustfs-vs-seaweedfs-vs-garage-which-minio-alternative-should-you-pick/)
- DevFlow code read: `src/app/server/object_store.py`, `runs.py` (upload archive, `download_artifact`), `runner.py` (`_archive_artifacts`), `run_retention.py`, `docker-compose.yml`, `.env.example`, `scripts/setup-env.sh`, `pyproject.toml`
