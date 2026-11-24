# Benchmarks

Briefs across the kinds of product the harness builds, each with **hidden
acceptance tests** written by a person from the brief and never shown to the
harness. A benchmark run's score is the share of hidden tests its product
passes; that, not a judgement after reading the code, is how the harness is
measured. See `docs/architecture-decisions.md ADR-0005`.

| Benchmark | Kind | Language | Hidden tests | Runner |
|---|---|---|---|---|
| `web-todo` | browser app | JavaScript | 10 | Playwright |
| `notes-api` | HTTP service | Python | 9 | pytest + httpx |
| `wordstats-cli` | command-line program | Python | 8 | pytest (as a process) |
| `textkit-lib` | library | Python | 8 | pytest (by import) |
| `fullstack-bookmarks` | page + its own service | JavaScript | 8 | Playwright (page and API) |
| `web-todo-react` | browser app | TypeScript, React | 10 (`web-todo`'s) | Playwright |
| `notes-api-js` | HTTP service | JavaScript | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-hono` | HTTP service | TypeScript, Hono (no pack) | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-go` | HTTP service | Go, net/http (LR.43 pack sweep) | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-rust` | HTTP service | Rust, axum (LR.43 pack sweep) | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-java` | HTTP service | Java, Spring Boot (LR.43 pack sweep) | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-csharp` | HTTP service | C#, ASP.NET Core (LR.43 pack sweep) | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-php` | HTTP service | PHP, Slim (LR.43 pack sweep) | 9 (`notes-api`'s) | pytest + httpx |
| `notes-api-ruby` | HTTP service | Ruby, Sinatra (LR.43 pack sweep) | 9 (`notes-api`'s) | pytest + httpx |
| `shortlinks-api` | HTTP service | Python (held out since 2026-11-17, LR.41: not tuned on) | 8 + 4 quality | pytest + httpx |
| `notes-api-falcon` | HTTP service | Python, Falcon (no pack) | 9 (`notes-api`'s) | pytest + httpx |
| `fullstack-bookmarks-py` | page + its own service | Python service, HTML/JS page | 8 (`fullstack-bookmarks`'s) | Playwright (page and API) |
| `tasks-api` | HTTP service with accounts and per-user data | Python | 10 | pytest + httpx |
| `tasks-api-change` | brownfield: a change to `tasks-api`'s product | Python | 15 (10 old, 5 new) | pytest + httpx |
| `notes-api-stale-knowledge` | HTTP service | Java, Spring Boot 4.2 (stale-knowledge trap; held out since 2026-11-25) | 9 (`notes-api`'s) + 8 + 1 quality | pytest + httpx |

The last two hold the `browser-react` and `node-http-api` stack packs to the
same hidden tests as their siblings: the briefs differ only in the stack they
ask for, and the tests reach the product only through the brief's interface.
They are coverage, not part of the gate below. `tasks-api` is the class the medium brief failed on live: sign-up, sign-in with a token, items per person, persistence, and a service started from `PORT` and `DATA_DIR` alone (its standard-library reference scores 10 of 10). `fullstack-bookmarks-py` does the same for a Python service behind the page (its standard-library reference scores 8 of 8). `notes-api-hono` asks for a stack no pack covers, so its run goes through
the setup stage (`app.stacks.custom_setup`): the agents set the project up and
the harness proves it; its reference (Hono on Node, TypeScript run directly)
scores 9 of 9.

`tasks-api-change` is the brownfield family (plan BW.3): its run starts from the tasks-api
reference (`base/`, uploaded into the workspace by `loop.sh bench`) with a brief for due dates,
a done filter and a summary. The hidden suite is tasks-api's ten tests and five for the change,
so a run that adds the features and breaks what was there loses points. The base scores 10 of 15
(every old test, no new one) and the reference 15 of 15.

## The stale-knowledge trap (`notes-api-stale-knowledge`)

Every family above already scores full hidden marks, so outside knowledge (the stack facts, the stuck lookup, the API
cards of HK.7) can move no hidden score on them (`reports/research/2026-11-24-agents-that-work-like-a-team.md`,
section (e)3). This family asks for a framework whose current major line is newer than a model's training data and
renamed or removed what the line before had; the hidden tests are `notes-api`'s nine, unchanged. Which framework is
data: `bench.json`'s `asked_release` (framework, ecosystem, package, major, latest release and dates, the day it was
checked), and the brief's Technical Constraints ask for that line in a person's words. Refresh both when the model
changes or the line ages into training data. The quality set is `notes-api`'s plus one test,
`quality/test_built_on_the_release_asked_for.py`: every version the product's manifests declare for the package is on
the asked major (a product that passes the nine tests on the older line it knows did not do what the brief says). The
scorer gives a quality set the benchmark's folder as `BENCH_DIR` for this. It is **held out** (`held_out_since`):
Measure runs only (`MEASURE=1 loop.sh bench notes-api-stale-knowledge`), since a fix written after its hidden failures
would tune the harness to one framework's changes.

Today's line, checked 2026-11-25:

- **Spring Boot 4.** 4.0.0 released 2025-11-20 (<https://github.com/spring-projects/spring-boot/releases/tag/v4.0.0>);
  the newest is 4.2.0, released 2026-11-19 (<https://github.com/spring-projects/spring-boot/releases/tag/v4.2.0>;
  Maven Central's `org/springframework/boot/spring-boot/maven-metadata.xml` gives `release` 4.2.0, after 4.0.0-4.0.10
  and 4.1.0-4.1.3).
- What the 4.0 line renamed or removed, from the Spring Boot 4.0 Migration Guide
  (<https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide>, read 2026-11-25):
  Jackson 3 is the JSON library, "with `com.fasterxml.jackson` becoming `tools.jackson`" (the 4.2.0 starter's
  `spring-boot-jackson` depends on `tools.jackson.core:jackson-databind` 3.1.8, not the 2.x artifact, so
  `import com.fasterxml.jackson.databind.ObjectMapper` no longer compiles without an added dependency), and an
  auto-configured `JsonMapper` replaces the `ObjectMapper` bean; `@MockBean` and `@SpyBean` were removed for
  `@MockitoBean` and `@MockitoSpyBean`; `@SpringBootTest` no longer gives MockMvc, `TestRestTemplate` or `WebClient`
  without `@AutoConfigureMockMvc` / `@AutoConfigureTestRestTemplate`, and `TestRestTemplate` moved to
  `org.springframework.boot.resttestclient`; `spring-boot-starter-web` is deprecated for `spring-boot-starter-webmvc`,
  each technology with its own `-test` starter (`@WebMvcTest` is now
  `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`, read from the 4.2.0 `spring-boot-webmvc-test` jar);
  Java 17 or later, Jakarta EE 11 and Servlet 6.1.

The harness's Java pack pins Spring Boot 3.4.5 (`stacks/packs/java_spring_api.py`); since LF.1311 a brief's stated line
wins at the scaffold (`stacks/stated_releases.py`): this brief is scaffolded on the newest 4.2 release the toolchain
runs, with the pack's Spring Boot 4 starters, smoke test and golden store, and falls back to 3.4.5, said in the stack
facts, only when that setup fails its own smoke test.

## How a benchmark is laid out

- `brief.md` - what the harness is given. Each brief has an **Interface**
  section stating what a user or a client program meets: the labels on a
  page's controls, a service's endpoints and its `start.sh`, the module a
  program runs as, the package a library is imported as. That is all the
  hidden tests rely on, so any implementation of the brief can pass them.
- `bench.json` - the kind of product and the runner.
- `hidden/` - the tests. Never copied into a workspace and never in the
  image (the image copies only `src/`).
- `base/` - a brownfield bench only (`"base"` in `bench.json`): the product the run starts from.
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
