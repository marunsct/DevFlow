# State of the loop

The one file every session reads first (plan MF.6). At most 150 lines, rewritten, not
appended: what is live, what is off, the last three runs, the next action. Everything
else is reference - `docs/HANDOVER.md` (rules, accounts, commands), `docs/monitoring-handover.md`
(mechanics and the run log), `docs/improvement-plan.md` (the plan). Narratives older than a
week are in `docs/archive/`.

**As of:** 2026-10-21 21:26 JST. Times are JST; containers and transcripts log UTC.

## Live now

| | |
|---|---|
| Run | **Measure gate run 1: run-650d812f** - `benchmarks/tasks-api/brief.md`, `DELIVERY=fast FRONTIER=false`, started 21:26 JST. Run 2 starts when it ends. **No deploys into either** (MF.4) |
| Frozen | harness commit **039ad84** (source as 9218b3e6: everything through LF.166) |
| Model | Qwen3.6-35B-A3B (owner, back from LFM2.5 at 21:19): 2 slots, 262,144 tokens; server sampling = Qwen's *precise coding* profile (temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence 0, repetition 1.0, max tokens 32,768); DevFlow context 260,000, reply ceiling 32,768 |
| Owner's model settings | the owner's; never changed by the loop |
| Peer sessions | none drive this workspace; this session is the only one that edits, deploys and starts runs |

## Off until measured (group 2 switches)

| Switch | Items | Module |
|---|---|---|
| `SHARED_FACTS` | CM.1 judges read the builders' facts | `app/agents/shared_facts.py` |
| `DECISION_LEDGER` | CM.2/EF.11 contract lines, CM.3 reports, PH.2 attempt records | `app/agents/ledger.py` |
| `FIX_CYCLE` | AY step 2 candidates from the fix's own model | `app/graph/bounded_fixes.py` |

Each module's `ON_BY_DEFAULT` turns its items on for the before/after runs.

## The last three runs

| Run | Brief | Result |
|---|---|---|
| run-f4f0030b | brief_medium | stopped at 15:08 JST in test round 2's fixes: 367 min, 383 calls, 1.66M output tokens, 13 fix stages, 1 of 13 criteria (5 of 34 tests); a findings run (LF.119-LF.140) |
| run-d48f049e | brief_medium | completed, acceptance 34/34, unit 30/30; 59% of its lines unreached (LF.120 built after it) |
| run-b7a20bad | brief_medium | failed after 4 attempts, acceptance 0/31; a findings run (LF.91-LF.107) |

No hidden tests exist for `brief_medium`: its results are hand audits (`loop.sh product`).

## Next actions

1. When the owner has Qwen3.6 serving and `loop.sh ready` says ALL READY: freeze the SHA (HEAD at that moment) and start **Measure (MF.4, MF.2)**: two gate runs on `benchmarks/tasks-api/brief.md`, `DELIVERY=fast FRONTIER=false`, one after the other, no deploys into them; score each with `loop.sh score <run> tasks-api`; `loop.sh kpi`. A bug found is filed for the Fix batch, not deployed.
2. The LFM day's fixes (LF.141-LF.166) are in the frozen SHA: they are general and stay.
3. Owner's decision pending: close the command loophole (a command writing files its stage may not) - a Fix-batch item, not for the frozen Measure SHA.
4. Group 2 after Measure, behind switches: PH.3, PH.1, CG.1-CG.2, RL.1-RL.3, IN.1, BW.1-BW.2, PN.1-PN.2, EV.2, the rest of AY; streaming loop-abort (proposed) to measure.

## Measuring

- KPIs: `loop.sh kpi <run>` -> `data/kpi/<run>.json` and `data/kpi/ledger.csv`; each row now carries
  `harness_commits`, `mixed_versions`, `served_model`, `switches_on` (MF.1), `gate_wait_minutes`,
  `accepted_criteria` and the cost per accepted criterion (MF.3).
- Comparing two harness versions: `python3 scripts/loop/kpi_ledger.py arms data/kpi/ledger.csv
  <commit-a> <commit-b> [benchmark]` - runs of exactly one commit, at least two per arm (MF.5).
- A mixed-version run is never compared.
- Backups: `loop.sh backup` (nightly), `loop.sh backup --check`, `loop.sh restore <dir> <new-db>` (OP.3).
- Notices: set `NOTIFY_WEBHOOK_URL` / `NOTIFY_EMAIL` (+ `SMTP_HOST`) for stalls and long gates (OP.2).
- Across every run: `loop.sh patterns [since]` - reply health per stage family, fix outcome by bundle size, recurring failures; read it at each deep analysis (LF.152).
- Reader corpus: `loop.sh corpus` (sizes, changes), `corpus harvest <run>`, `corpus accept`; the suite replays `data/corpus` (RC).

## Rules that are never optional

`AGENTS.md`. In short: the model is the owner's (`loop.sh ready` must say ALL READY);
fixes are stack-agnostic (packs, `plugins/seed.py`, per-language tables); every fix has a
test proven failing on the old code; `loop.sh suite` green but for the three S3 tests;
commit and push after every change (`git push main harness-hardening-session`); no secrets
printed; the operator account only (`docs/HANDOVER.md` §3).

## Loop cost

Session reading at start, before this file existed: about 12,000 lines (MF.6). Now: this
file, then only what the next action needs. Each session notes its fixes and their cost here
when it hands over.

| Session | Fixes | Notes |
|---|---|---|
| 2026-10-21 (langchain-90) | LF.119-LF.138, CM.1-CM.3, EF.11, AY.2, PH.2, MF.1/3/5 | taken over from the earlier window at 14:18 JST |
