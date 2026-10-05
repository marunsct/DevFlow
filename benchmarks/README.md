# Benchmarks

Briefs across the kinds of product the harness builds, each with **hidden
acceptance tests** written by a person from the brief and never shown to the
harness. A benchmark run's score is the share of hidden tests its product
passes; that, not a judgement after reading the code, is how the harness is
measured. See `docs/redesign-software-company.md`.

| Benchmark | Kind | Language | Hidden tests | Runner |
|---|---|---|---|---|
| `web-todo` | browser app | JavaScript | 10 | Playwright |
| `notes-api` | HTTP service | Python | 9 | pytest + httpx |
| `wordstats-cli` | command-line program | Python | 8 | pytest (as a process) |
| `textkit-lib` | library | Python | 8 | pytest (by import) |
| `fullstack-bookmarks` | page + its own service | JavaScript | 8 | Playwright (page and API) |

## How a benchmark is laid out

- `brief.md` - what the harness is given. Each brief has an **Interface**
  section stating what a user or a client program meets: the labels on a
  page's controls, a service's endpoints and its `start.sh`, the module a
  program runs as, the package a library is imported as. That is all the
  hidden tests rely on, so any implementation of the brief can pass them.
- `bench.json` - the kind of product and the runner.
- `hidden/` - the tests. Never copied into a workspace and never in the
  image (the image copies only `src/`).
- `reference/` - a small implementation that must score 100%. It proves the
  hidden tests are right before they are used to judge anything; a hidden
  test the reference fails is a bug in the test.

## Running one

```
LOOP_USER=... LOOP_PASSWORD=... scripts/loop/loop.sh bench web-todo   # start a run from the brief
scripts/loop/loop.sh score                                            # when it finishes: score it
```

`score` copies the product out of the run's workspace, starts it the way its
brief says (a static server for a page, `start.sh` for a service, `python -m`
for a program, an import for a library), runs the hidden tests against it and
writes `data/bench/<run>.json`.

`score` also records what the harness itself concluded - the run's status and
its locked acceptance suite's last result - and marks a **false acceptance**: a
run the harness finished whose product fails hidden tests. `loop.sh
bench-report` (`scripts/bench/report.py`) totals them per benchmark; the
false-acceptance rate, not the mean score, says whether a finished run can be
handed over unread.

`loop.sh mutate [run] [n]` (`scripts/bench/mutate.py`) measures the run's own
locked suite: it makes n small changes to the product's source (a comparison
turned round, a condition flipped), runs the suite the way the harness does,
and counts how many it catches. That is a floor on how well the tests check
what they check; a requirement no test checks shows up only as a false
acceptance.

To check a benchmark itself, score its reference:

```
python scripts/bench/score.py benchmarks/<name>/reference benchmarks/<name> /tmp/out.json   # inside the worker
```

## The improvement loop's gate

A run is **clean** when its product scores 100% on the hidden tests and the run
needed no harness fix. Any harness fix resets the current stage's count.

1. `web-todo`: two consecutive clean runs.
2. `notes-api`, `wordstats-cli`, `textkit-lib`: one clean run each.
3. `fullstack-bookmarks`: two consecutive clean runs.
4. `tests/brief_medium.md`, audited by hand as before, then `tests/brief_high.md`.
