# State of the loop

The one file every session reads first (plan MF.6). At most 150 lines, rewritten, not
appended: what is live, what is off, the last three runs, the next action. Everything
else is reference - `docs/HANDOVER.md` (rules, accounts, commands), `docs/monitoring-handover.md`
(mechanics and the run log), `docs/improvement-plan.md` (the plan). Narratives older than a
week are in `docs/archive/`.

**As of:** 2026-10-21 15:15 JST. Times are JST; containers and transcripts log UTC.

## Live now

| | |
|---|---|
| Run | none. Gate run 3 (run-f4f0030b) was stopped at 15:08 JST at the owner's word: little left to learn on the old model |
| Model | **LFM2.5-24B-A2B** (owner's switch, 15:08 JST): 3 slots, 131,072 tokens as started; the owner's 186,000 setting is capped at the slot by `context_budget` |
| LFM measured | `loop.sh fitness --edits`: FIT 5/5, edits and whole files 100% well formed; `reasoning-probe run`: it reasons (about 2.3-3.3k output tokens a planning reply), no thinking switch turns that off (`thinking_off` -27%, reasoning still present) |
| Deployed | worker image 3129aa1 (LF.138, MF.1/MF.3/MF.5); RC, OP, CH, IN.2, BW.3, LF.139-LF.140 are on the branch, not yet deployed |
| Owner's model settings | reply ceiling 0 (none), context window 186,000, thinking default - the owner's; never changed by the loop |
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

1. Deploy HEAD - the frozen SHA for the Measure cycle; then `loop.sh corpus harvest` run 3 (its image lacked the corpus) and the product review doc (Claude Docs `0ba22658-e6f1-4b33-adbd-87c6cac83dae`).
2. **Measure (MF.4, MF.2):** two gate runs on **`benchmarks/tasks-api/brief.md`** on LFM2.5, `DELIVERY=fast FRONTIER=false`, no deploys into them; score each with `loop.sh score <run> tasks-api`. A bug found is filed for the Fix batch, not deployed.
3. Group 1 of Appendix 7 left: SF.1, SF.2, EV.1 (done: MF.1-MF.6, RC.1-RC.3, OP.1-OP.4, CH.1-CH.3, IN.2, BW.3). Built on the branch while Measure runs on the frozen image.
4. Group 2 next, behind switches: PH.3, PH.1, CG.1-CG.2, RL.1-RL.3, IN.1, BW.1-BW.2, PN.1-PN.2, EV.2, the rest of AY. M.4 (fix-stage reasoning) is the owner's call - on LFM the replies are a tenth of Qwen's, so it may not be needed.

## Measuring

- KPIs: `loop.sh kpi <run>` -> `data/kpi/<run>.json` and `data/kpi/ledger.csv`; each row now carries
  `harness_commits`, `mixed_versions`, `served_model`, `switches_on` (MF.1), `gate_wait_minutes`,
  `accepted_criteria` and the cost per accepted criterion (MF.3).
- Comparing two harness versions: `python3 scripts/loop/kpi_ledger.py arms data/kpi/ledger.csv
  <commit-a> <commit-b> [benchmark]` - runs of exactly one commit, at least two per arm (MF.5).
- A mixed-version run is never compared.
- Backups: `loop.sh backup` (nightly), `loop.sh backup --check`, `loop.sh restore <dir> <new-db>` (OP.3).
- Notices: set `NOTIFY_WEBHOOK_URL` / `NOTIFY_EMAIL` (+ `SMTP_HOST`) for stalls and long gates (OP.2).
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
