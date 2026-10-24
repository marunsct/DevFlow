# One writer, independent checkers: a review of how many agents the harness needs

Owner question 2026-10-24: the setup stage already builds the product before any sprint starts. Do bugs
come from the wrong agent building it? If one agent can write everything, why keep so many agents?

Status: **review and proposal; nothing built.** Rows SW.1-SW.5 in `docs/improvement-plan.md`.

## 1. What our own data says

The product was written by the setup stage in both Ornith runs, and by separate builders (work orders,
then one drafting call per file) in the Qwen runs. Same benchmark (tasks-api), all-on harness,
completed runs only.

| Run | Who wrote the product | Hidden | Quality | Defects raised | By source |
|---|---|---|---|---|---|
| 8cced4a9, f13f7438, 3bfd71ee, 77f7752f, 1409658f (Qwen) | lead, work orders, per-file drafting | 10/10 each | 0.85-1.0 | 7, 4, 8, 6, 3 | language service 6, acceptance suite 15, test round 6 |
| 2b891f3f (Ornith, mixed) | the setup stage | 10/10 | 1.0 | 2 | cross-file 1, test round 1 |
| cfb01bcc (Ornith, clean) | the setup stage | 10/10 | 0.86 | 1 | test round 1 |

- **Outcome quality is the same** (every completed run scored 10/10 hidden).
- **Defects are not.** A product written file by file raised 3 to 8 defects, mostly of two kinds: a type or
  import error between files (the language service), and behaviour that differs from a locked criterion
  (the acceptance suite). The setup-built products raised none of either kind.
- **Reading:** this matches Cognition's finding that parallel writers make conflicting implicit choices.
  Per-file drafting is parallel writing against a shared specification. One agent writing in sequence,
  holding the whole design and running the smoke tests as it goes, does not conflict with itself.
- **Caveats, stated plainly:** two different models; two Ornith runs against five Qwen runs; one small
  benchmark (about 360 lines of product). This is a strong pointer, not a proof.

Where the tokens went in the clean tasks-api run (735,000 output tokens):

| Role | Share |
|---|---|
| QA writes and reviews the suite | 27% |
| Architect and its review | 27% |
| Consults and intake | 8% |
| Advice, milestone and security reviews | 12% |
| **Setup (which wrote the product)** | **12%** |
| Sprint plan, lead, work orders, fixers | 7% |

**Writing the product was the cheapest thing the harness did.** The roles around it cost five times as much.

## 2. What each role earns

A role earns its place by what it catches or enables, not by what it writes.

| Role | Earns its place? | Evidence |
|---|---|---|
| Independent acceptance suite, written from the brief, locked | **Yes** | It is what turned "looks done" into hidden 10/10; the clean run's suite found real deviations before release |
| Clean-context reviews (spec, milestone, security) | **Partly** | Spec review sent the specification back every time and the revisions were real; the advice reviews found almost nothing on a product this size |
| Fixers, one defect at a time | **Yes** | One defect, closed in one round |
| Architect, consults, intake | **For the contract, yes; at this cost, unproven** | 35% of tokens; the specification feeds QA and review, but a short plan may do for a small product |
| Lead, work orders, per-file drafting, builders | **No, on a small product** | Produced the defects above; in the Ornith runs the lead planned three times with nothing to build |
| Setup | **Yes, for its own job** | Proves the toolchain and the smoke tests; its overreach is the real builder today, unmanaged |

## 2b. Why one agent could build the whole product (access, tools, context)

Checked against the transcripts and the code, for the setup agent and for the builders it replaced.

| | Setup agent (built the product) | Builders in the pipeline (Qwen runs) |
|---|---|---|
| Tools | write, edit, delete, move, read, ls, run command, run validation, package lookup, docs | the same set, minus package lookup |
| Where it may write | **anywhere in the project.** The write fences name the acceptance author, test rounds and the testing work order; a stage called `stack_setup_` is in none of them | only the files its work order lists ("belongs to another work order") |
| What it sees of the design | the specification's files, testing, configuration and library-call sections in its request, the rest readable in `docs/technical_specification.md`, and the whole project in memory | one drafting call per file: its own specification entry plus neighbours capped at 24,000 characters |
| Feedback | **closed loop:** write, run the unit and acceptance smoke tests, read the failure, edit, in one conversation (19 to 23 commands, 9 validations in 34 calls) | **open loop:** a file is drafted in one call with no run; the compiler and the suite find the mismatches later |
| Context per call | starts at 18,000 tokens, grows to 37,000-57,000 (one spike to 92,000); a 360-line product | 8,000-14,000 for a drafted file; 64,000-80,000 for a specialist |
| Order | one writer, in sequence | several files drafted at once from a shared specification |

So the single agent did not succeed by being cleverer. It had three things the pipeline did not: **no write fences, the whole design in view, and a run-and-fix loop inside one conversation**. The pipeline's defects (type and import mismatches between files, behaviour differing from a criterion) are what an open loop with narrow views produces. That is why "who writes" matters less than "with what view and what feedback".

## 2c. Where one agent breaks: size

The owner's concern is right, and the numbers show where. The product here is about 360 lines, roughly 5,000 tokens of source, and the setup agent's context was already 37,000-57,000 tokens (the specification, the request, tool outputs) with a 262,144-token window. Source scales with the product; the overhead does not shrink:

| Product | Source in context | Realistic call context | Verdict for one agent |
|---|---|---|---|
| 360 lines (this benchmark) | about 5,000 tokens | 40,000-60,000 | fine |
| 3,000-5,000 lines | 40,000-70,000 tokens | 100,000-130,000 | at the edge: reasoning quality drops with length ("context length alone hurts", measured by others), every call re-reads more, cache helps but not reasoning |
| 20,000+ lines | 250,000+ tokens | exceeds the window | impossible without partitioning |

(Estimates: about 12-14 tokens a line; the harness already ranks and truncates its project memory, `MEMORY_CHARACTERS` 60,000, for this reason.)

The principle that follows: **an agent is a context partition, not an org-chart role.** Split a writer only when
its working set would pass a budget, and split along the specification's own module boundaries:
- each module's writer is single-threaded, keeps the closed run-and-fix loop, and sees only its module, the
  interface contract and a compact ledger of what earlier modules declared (not their full text);
- modules with a frozen interface may be written in parallel; modules that share state are written in order;
- a final integration run measures the whole, and fixers work one defect at a time.

This is what the pipeline tried to do with work orders and drafting, but without the closed loop and with views
too narrow to see the neighbours' contracts. The fix is to keep the partitioning and add what was missing.

## 3. What others do

Anthropic: start with the simplest solution and add structure only where it demonstrably helps; a chain makes
each call easier. Cognition: "writes stay single-threaded and the additional agents contribute intelligence
rather than actions"; a reviewer with a clean context gave "a notable improvement"; arbitrary agent networks
are "mostly a distraction". Agentless: a fixed pipeline of small, checked steps matched agent systems.
Aider: plan and edit as separate calls. Together: **separate the writing from the checking, keep the writing
single-threaded, keep the checking independent.**

## 4. Options

| | Option | Gain | Risk |
|---|---|---|---|
| A | Keep as is (the setup stage builds, sprints review) | Works, 10/10 | The build roles are untested; QA sees the product before writing its suite, so independence is weaker; setup minutes are unmanaged; will not scale to large products |
| B | One agent for everything, including the suite and the review | Simplest, cheapest | Loses independent checking: the author of the code writes its tests and reviews it. This is the one thing the data says to keep |
| C | Cut the pipeline back to the roles that earn their place (below) | Fewer defects at small sizes, less cost, scales by size | A new stage to build and measure |
| D | Fix setup overreach only (write the smoke path, leave the rest to a build stage) | Clean roles again | Brings back the per-file drafting defects unless the build stage is also single-writer |

## 5. Recommendation: C, "one writer, independent checkers", size-adaptive

1. **Setup** proves the toolchain and the smoke tests and stops (its three recent defects are fixed).
2. **QA writes the suite from the brief, before any product code**, and the suite is locked. It cannot be
   shaped to the code, which restores independence and gives the builder a red-to-green target.
3. **One builder** writes the product in sequence from the specification and the locked suite, in the order
   the specification gives, **running the unit and acceptance runs as it goes (the closed loop that made the
   setup agent work)**. It replaces lead, work orders, per-file drafting and per-role builders for products whose
   estimated working set fits a context budget (about 60,000 tokens of source, decided at run time from the
   specification's file and criterion counts, as the small/large rule already does).
4. **Above that budget** the builder is partitioned along the specification's modules: each part is a
   single-threaded writer with the closed loop, its module, the interface contract and a compact ledger of what
   earlier parts declared (`docs/work-batching.md`); parts with a frozen interface may run side by side.
   Every writer, at every size, gets the run-and-fix loop and no narrower a view than the contract.
5. **Checkers stay independent and unchanged:** the spec review, one clean-context milestone and security
   review, fixers one defect at a time. Advice reviews run only where earlier runs showed findings.
6. **Later, as its own arm:** a shorter specification for small products (core parts, one review pass), since
   the architect is the single largest cost.

## 6. How it avoids new defects

- A switch `SINGLE_BUILDER`, code default off, with a size gate and a fallback to the present pipeline on any
  failure of the builder stage.
- **Shadow first:** record what it would have done (size, order, stage) on the next runs, act on nothing.
- **A measured arm before default-on (MF.4):** same model, tasks-api, two runs each. Arm A is the present
  setup-built flow; arm B is the new flow. Compare hidden, quality, mutation, defects by source, minutes,
  tokens. It must not lower hidden, quality or mutation, and must lower minutes or defects; else it is parked.
- A harder benchmark (a larger product) before it is trusted at size.
- `loop.sh effects` reports fires, fall-backs and defects by source per arm.

## 7. Build order

| Row | What |
|---|---|
| SW.1 | Report defects by source and who wrote the product per run (`loop.sh scan`), so this comparison is a standing number and not a one-off |
| SW.2 | QA before the build: reorder so the suite is written before product code; setup stops at the smoke path (keep the three setup fixes) |
| SW.3 | The single builder stage for small products, behind `SINGLE_BUILDER`, with the fallback |
| SW.4 | The measured arm: two runs each, one model |
| SW.5 | Module-by-module mode for large products (shares the carry ledger with WB) |

Not recommended: option B. The data supports fewer *writing* roles, not fewer *checking* roles.
