# How open-source harnesses search the web without paid keys, and what this harness should build

Date: 2026-11-25 (JST). Research only: no code was changed. File and line references are to commit `40d5fe3a`
(HK.5 landed as LF.1291 while this was written). Sources were read on 2026-11-24; project source files
were read on GitHub, not only READMEs. Where something could not be confirmed from a primary source it is marked
**unverified**. Plan items are numbered KS.n (keyless search) and are written to merge with HK.3, HK.5 and HK.12 of
`reports/research/2026-11-24-agents-that-work-like-a-team.md`.

## (a) The short answer

**Open-source harnesses do not have a secret free search.** Read in source, 26 projects fall into five groups:

1. **A paid key by default** (the largest group among coding agents): OpenHands (Tavily), gpt-researcher (Tavily),
   LangChain Open Deep Research (Tavily or the model vendor's own search), LibreChat (Serper + Firecrawl), CrewAI
   (every general search tool is keyed), Cline (vendor-native search or Exa), MindSearch (Bing key).
2. **A self-hosted SearXNG** (the only keyless backend almost everyone supports): Vane (formerly Perplexica) and
   local-deep-research by default; Khoj and Morphic in their Docker Compose files; Goose, STORM, Open WebUI,
   AnythingLLM, gpt-researcher and LibreChat as an option. This is what this harness already runs.
3. **Scraping DuckDuckGo** through the `ddgs` library or directly (smolagents, LlamaIndex, STORM, Open WebUI,
   MindSearch, AnythingLLM's fallback, Goose's last resort). Everyone who relies on it wraps it in retries, because
   it is rate-limited and breaks several times a year.
4. **Someone else's hosted endpoint, keyless for now**: Continue's `@web` (a Continue-run proxy), Open Interpreter
   0.4 (its own API), AnythingLLM (You.com, 100 queries a day per address), Jan (an Exa keyless endpoint).
5. **No search at all**: SWE-agent, Aider (`/web <url>` only reads a page), Roo Code (browser use removed; MCP only).

Three further findings matter more than the list:

- **General web search from a self-hosted instance is failing today.** Through SearXNG, Google returns 403 (issue
  open since 2026-10-11), Startpage and Mojeek ship switched off because of proof-of-work CAPTCHAs, Brave and Qwant
  suspend, Bing returns irrelevant results. This matches what this harness measured on 2026-11-20
  (`src/app/tools/web_search.py:53-56`).
- **The reliable free part is official APIs, not search engines**: Stack Exchange, GitHub, the package registries,
  MDN, OSV, Wikipedia. This harness already asks these first (`src/app/tools/lookups.py:10-13`), which is ahead of
  every project read. No project read asks Stack Exchange or a library's issue tracker directly.
- **Nobody solves concurrency.** Caching, rate limiting and backoff are nearly absent in the projects read. The few
  exceptions are named in section (b). Production design has to come from the sources' own published limits.

**So the recommendation is not to copy another harness's search backend.** It is to finish what this harness started:
read answers through each site's official channel, keep code intact, tell "refused" from "nothing found", and put
one shared cache and one rate limiter in front of every source. Section (e) ranks ten items.

The most costly gap found, verified on this machine: **the page reader cannot read Stack Overflow at all** (HTTP 403),
although search results rank Stack Overflow first (`src/app/tools/web_search.py:61-64`).

## (b) Comparison of projects

### Coding agents and agent frameworks

| Project | Search backend | Keyless by default? | Page reader | Notable handling |
|---|---|---|---|---|
| [OpenHands](https://github.com/All-Hands-AI/OpenHands/blob/1.0.0/openhands/core/config/mcp_config.py) | Tavily MCP only | No | BrowserGym accessibility tree; newer SDK: browser-use + `mcp-server-fetch` | Prompt text: switch site on 403 or CAPTCHA |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent/blob/main/tools/web_browser/config.yaml) | None | n/a | Playwright screenshots, for testing a site | No search, no text extraction |
| [Aider](https://github.com/Aider-AI/aider/blob/main/aider/scrape.py) | None (`/web <url>`) | n/a | Playwright or httpx, BeautifulSoup trim, pandoc to Markdown | No truncation, cache or robots check |
| [Open Interpreter 0.4.2](https://github.com/OpenInterpreter/open-interpreter/blob/v0.4.2/interpreter/core/computer/browser/browser.py) | The project's hosted API | Keyless, hosted | Selenium + html2text, summarised by a small model | Current HEAD is a different codebase |
| [Goose](https://github.com/block/goose/blob/main/crates/goose/src/skills/builtins/web_search.md) | Tavily if a key, SearXNG if a URL, else `uvx ddgs` | Yes (ddgs) | `curl` + html2text, or the Fetch MCP server | 15,000-character cut; text says obey robots, stop on CAPTCHA |
| [Cline](https://github.com/cline/cline/blob/main/sdk/packages/core/src/extensions/tools/executors/web-fetch.ts) | Vendor-native search or Exa plugin | No | fetch + tag strip; VS Code: puppeteer + cheerio + turndown | 5 MB cap, 30 s |
| [Roo Code](https://github.com/RooCodeInc/Roo-Code/blob/main/CHANGELOG.md) | None | n/a | None (browser use removed) | MCP only |
| [Continue](https://github.com/continuedev/continue/blob/main/core/context/providers/WebContextProvider.ts) | `@web`: Continue-run proxy | Keyless, hosted | `@url`: Mozilla Readability + Markdown | Engine behind the proxy not visible |
| [smolagents](https://github.com/huggingface/smolagents/blob/main/src/smolagents/default_tools.py) | ddgs; or direct DuckDuckGo lite scrape; Bing RSS; keyed APIs | Yes | requests + markdownify, 40,000 characters | 1 query a second limiter |
| [CrewAI tools](https://github.com/crewAIInc/crewAI/tree/main/lib/crewai-tools/src/crewai_tools/tools) | Serper, Brave, Exa, Tavily and others | No keyless search found | requests + BeautifulSoup text | Checks every redirect hop for private hosts |
| [AutoGen](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-ext/src/autogen_ext/agents/web_surfer/_multimodal_web_surfer.py) | A Playwright browser pointed at bing.com | Yes (browser) | MarkItDown, visible text, 8,192-character views | Model summarises the page |
| [browser-use](https://github.com/browser-use/browser-use/blob/0.11.0/browser_use/tools/service.py) | 0.11: browser to DuckDuckGo ("less captchas"). HEAD: its paid search API | 0.11 yes; HEAD no | Page Markdown, 30,000 characters with an offset | CAPTCHA solving only in its paid cloud |
| [LlamaIndex](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-duckduckgo/llama_index/tools/duckduckgo/base.py) | DuckDuckGo tool | Yes | None in this tool | Pinned to an old `duckduckgo-search` (<7) |
| [MCP fetch server](https://github.com/modelcontextprotocol/servers/blob/main/src/fetch/src/mcp_server_fetch/server.py) (used by Goose, OpenHands) | None | n/a | readabilipy + markdownify, 5,000 characters with `start_index` | The only one that checks robots.txt in code |

### Research assistants and chat applications

| Project | Search backend (default in bold) | Keyless out of the box? | Page reader | Ranking and summarising | Cache and rate handling |
|---|---|---|---|---|---|
| [gpt-researcher](https://github.com/assafelovic/gpt-researcher/blob/master/gpt_researcher/config/variables/default.py) | **Tavily**; duckduckgo, searx, arxiv, pubmed, bing, google, serper, brave and more | No; `RETRIEVER=duckduckgo` or `searx` | requests + BeautifulSoup; PyMuPDF for PDFs; optional browsers, Firecrawl | 1,000-character chunks, embedding similarity filter | URL dedupe, 15 workers, optional delay |
| [Vane (ex-Perplexica)](https://github.com/ItzCrazyKns/Vane/blob/master/src/lib/searxng.ts) | **SearXNG only**, bundled | Yes | Playwright + Mozilla Readability | Embedding rerank of snippets; quality mode: model picks 3 pages and extracts facts | 10 s timeout; none |
| [Morphic](https://github.com/miurla/morphic/blob/main/app/api/advanced-search/route.ts) | **Tavily** in code, **SearXNG** in Compose | Yes in Docker | fetch + tag strip; Jina Reader; self-hosted crawl4ai | Keyword scoring (phrase, word hits, title) | **Redis cache, 1 hour**; second provider on failure |
| [Khoj](https://github.com/khoj-ai/khoj/blob/master/src/khoj/processor/tools/online_search.py) | Serper, Exa, Firecrawl, Google, **SearXNG** (Docker) | Yes in Docker | aiohttp + BeautifulSoup + markdownify, else Exa, Olostep, Firecrawl | Model writes sub-queries and extracts per page | Reader fallback chain |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/configuration.py) | **Tavily**, vendor-native search, MCP | No (legacy code had DuckDuckGo) | Tavily's raw content | Per-page model summary of the first 50,000 characters | Legacy: 3 retries with backoff |
| [Open WebUI](https://github.com/open-webui/open-webui/blob/main/backend/open_webui/routers/retrieval.py) | 34 engines, **none chosen** | Yes if DuckDuckGo, SearXNG or YaCy is picked | requests + BeautifulSoup; Playwright; Firecrawl | Pages into a vector store, then normal retrieval | 3 results, 10 concurrent loads |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm/blob/master/server/utils/agents/aibitat/plugins/web-browsing.js) | **You.com keyless**, then DuckDuckGo HTML scrape; 19 providers | Yes | Puppeteer, then fetch; turndown | None | 100 a day per address, then fallback |
| [LibreChat](https://github.com/danny-avila/agents/blob/main/src/tools/search/search.ts) | **Serper**, SearXNG, Tavily | No | Firecrawl (self-hostable) | Jina or Cohere rerank service | 10 s timeouts |
| [Jan](https://docs.jan.ai/desktop/web-search) (docs only) | **Exa keyless endpoint**; Tavily, SearXNG | Yes | `web_fetch` | Not verified | Not verified |
| [local-deep-research](https://github.com/LearningCircuit/local-deep-research/blob/main/src/local_deep_research/web_search_engines/rate_limiting/tracker.py) | **SearXNG**; arXiv, Wikipedia, PubMed, GitHub and keyed ones | Yes | trafilatura, then readability, justext, newspaper | Model picks relevant results in batches | **Learns a wait time per engine**, kept in a database; detects challenge pages |
| [STORM](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/rm.py) | You.com, Bing, Brave, Serper, DuckDuckGo, Tavily, SearXNG; no default | Yes with DuckDuckGo or SearXNG | httpx + trafilatura | MiniLM cosine over 1,000-character snippets | DuckDuckGo: backoff, 8 tries |
| [MindSearch](https://github.com/InternLM/lagent/blob/main/lagent/actions/web_browser.py) | **Bing key**; DuckDuckGo, Brave, Serper | Yes with DuckDuckGo | requests + BeautifulSoup, first 8,192 characters | Model picks up to 4 results to open | **600 s cache**, 3 retries, proxy option |
| [Search-R1](https://github.com/PeterGriffinJin/Search-R1/blob/main/docs/retriever.md) | **A local index** of a Wikipedia dump (BM25 or e5) | Yes (not the live web) | n/a | Optional cross-encoder | None |

### What the tables show

- **Page reading is plain HTTP plus a text extractor** almost everywhere, with a 4-20 second limit and a hard cut
  between 5,000 and 50,000 characters. A headless browser is the default only in Vane, AnythingLLM and Aider.
- **Ranking is cheap**: embedding similarity over snippets, or a model picking result numbers. A per-page model
  summary is the main way to save context (Vane, Khoj, Open Deep Research, local-deep-research). HK.3(f) plans the
  same.
- **robots.txt is checked in code only by the MCP fetch server.** This harness already does it
  (`src/app/tools/page_reader.py:187-200`).
- **Protection against reading private addresses is now standard.** This harness's is stricter than any read
  (`page_reader.py:142-182`: address pinned per hop).
- **The `ddgs` library is not a stable base.** Its [release notes](https://github.com/deedy5/ddgs/releases) show the
  package renamed (July 2025), functions removed (December 2024), and the Google backend switched off and on four
  times between October 2025 and August 2026. It now scrapes Bing, Brave, Google, Mojeek, Startpage, Yandex and
  Yahoo as well as DuckDuckGo.

## (c) What is reliable now, and what is fragile

| Backend | Verdict | Evidence (date) |
|---|---|---|
| SearXNG developer engines (Stack Exchange sites, GitHub, MDN, registries, Arch wiki, Wikipedia) | **Reliable** | Enabled by default, keyless ([configured engines](https://docs.searxng.org/user/configured_engines.html)); measured here 40-110 results (`web_search.py:53-56`) |
| Stack Exchange API | **Reliable with a key** | 300 a day per address without a key (live check from this machine: `quota_max` 300); 10,000 with a key ([throttle docs](https://api.stackexchange.com/docs/throttle)). Whether a public key is still free to register in 2026 is **unverified** |
| GitHub REST API | **Reliable with a token** | Search 10 a minute without, 30 with; core 60 an hour without, 5,000 with ([rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)) |
| Package registries, OSV | **Reliable** | PyPI: no edge rate limit ([docs](https://docs.pypi.org/api/)); OSV: no limit, no key ([FAQ](https://google.github.io/osv.dev/faq)); crates.io: 1 a second with an identifying User-Agent; Maven Central is phasing in 429s for heavy addresses ([FAQ](https://central.sonatype.org/faq/429-error/)) |
| Wikimedia APIs | **Reliable** | 10 a minute unidentified, 200 a minute with a compliant User-Agent ([limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)) |
| SearXNG: DuckDuckGo | **Usable with care** | The one general engine on by default; a CAPTCHA wave closed 2026-09-04 ([#6596](https://github.com/searxng/searxng/issues/6596)) |
| Jina Reader (hosted) | **Usable with care** | 20 requests a minute without a key ([jina.ai/reader](https://jina.ai/reader/)); sends the address to a third party |
| Marginalia API | **Usable with care** | Shared `public` key often rate-limited; non-commercial licence ([API page](https://about.marginalia-search.com/article/api/), 2025-12-08) |
| `ddgs` library | **Fragile** | See above; still scraping |
| SearXNG: Bing | **Fragile** | "Results often unrelevant", open since 2025-07 ([#4964](https://github.com/searxng/searxng/issues/4964)) |
| SearXNG: Brave, Qwant | **Fragile** | Suspended for weeks on a stock setup, 2026-10 ([#6866](https://github.com/searxng/searxng/issues/6866)) |
| Context7 free tier | **Fragile as a free dependency** | Reported cut to about 1,000 calls a month; sources disagree ([plans](https://context7.com/plans)) |
| SearXNG: Google | **Avoid** | HTTP 403, open 2026-10-11 and still open ([#6835](https://github.com/searxng/searxng/issues/6835)) |
| SearXNG: Startpage, Mojeek | **Avoid** | Shipped `inactive: true`, "uses a Proof Of Work captcha" ([settings.yml](https://raw.githubusercontent.com/searxng/searxng/master/searx/settings.yml)) |
| Brave Search API | **Not free any more** | Free tier ended February 2026: $5 a month of credit, card required, storing results needs a custom plan ([brave.com/search/api](https://brave.com/search/api/)) |
| Mojeek API | **Paid** | No confirmed free tier |

Other facts that shape the design:

- **SearXNG has no result cache.** Every query goes upstream. More instances on one address add no capacity,
  because the upstream block is per address.
- **SearXNG's own Stack Exchange and GitHub engines call the same APIs this harness calls directly**
  ([stackexchange.py](https://github.com/searxng/searxng/blob/master/searx/engines/stackexchange.py) uses
  `api.stackexchange.com/2.3/search/advanced`; [github.py](https://github.com/searxng/searxng/blob/master/searx/engines/github.py)
  uses `api.github.com/search/repositories`, sorted by stars). They spend the same per-address quota, keyless.
- **Suspension times differ between the SearXNG docs and the shipped file** (access denied: 86,400 s in the docs,
  180 s shipped). They should be set explicitly.
- **Self-hosted documentation exists**: [DevDocs](https://github.com/freeCodeCamp/devdocs) is maintained and
  self-hostable. Stack Exchange data dumps moved behind a login with a no-model-training condition in 2024, so they
  are not a clean base for an index. About 6-28% of sites publish `llms.txt` (estimates vary by sample).
- **Extraction quality**: on news-article benchmarks trafilatura scores highest (F1 0.958), Mozilla Readability
  0.947, readability-lxml 0.922; plain converters such as html2text score 0.66
  ([trafilatura evaluation](https://trafilatura.readthedocs.io/en/latest/evaluation.html),
  [article-extraction-benchmark](https://github.com/scrapinghub/article-extraction-benchmark)). **Neither benchmark
  measures code blocks**, and trafilatura has an open bug on code indentation (#1136, 2026-11-11). No head-to-head
  test of code preservation was found.
- **Legal context**: Google's terms forbid automated access against its machine-readable instructions. Google sued
  SerpApi in December 2025 over circumventing its blocks; the current status of that case is **unverified**.

## (d) Gap analysis of this harness

### What is already at or above the best open-source practice

- Official free sources before any search engine, chosen by the harness and not the model (`lookups.py:1-29`,
  `SOURCES` at 270-279).
- Only a cleaned error line leaves the machine, now through the one outbound gate built as HK.5
  (`src/app/tools/outbound.py`, LF.1291; `lookups.py:88-94`).
- Daily caps per source and a 7-day answer cache (`lookups.py:68-71`, 364-382).
- A page reader that pins the checked address on every redirect hop and obeys robots.txt
  (`page_reader.py:142-200`).
- A live probe of every source before a run (`scripts/loop/lookup_ready.py`).
- Developer engines asked first, general engines only when they find too little (`web_search.py:57-59`, 98-111).

### Gaps, most costly first

| # | Gap | Evidence | Best practice it falls short of |
|---|---|---|---|
| 1 | **Stack Overflow pages cannot be read.** The reader gets HTTP 403. | Run on this machine 2026-11-24 with `page_reader.read`: "The page answered 403, and no browser is available". Its robots.txt is `User-agent: * Disallow: /`. Yet it is the first answering host (`web_search.py:61-64`) | Read through the Stack Exchange API by question id, which the site offers for this |
| 2 | **The browser fallback never runs.** | `page_reader.py:316` needs Python `playwright`; `pyproject.toml` does not list it; not importable in the project environment (checked). www.npmjs.com also answers 403 | A built-but-silent mechanism: either make it work or remove it |
| 3 | **GitHub pages are read as HTML.** A changelog file page returns interface text first ("Files, Expand file tree, Copy path, Blame"); an issue returns "New issue, Copy link" repeated. | Same run: `github.com/.../blob/main/CHANGELOG.rst` and `/issues/684` | Raw file host and REST API for files, issues with comments, releases |
| 4 | **Code loses its shape.** `_plain` joins all whitespace, so a multi-line code answer becomes one line; the reader keeps `<pre>` text but adds no fence or language. | `lookups.py:117-120`; `page_reader.py:250-253`, 280 | Markdown output with fenced code (Aider, Cline, MCP fetch, Khoj) |
| 5 | **A refused source looks the same as "nothing found".** Any status other than 200 returns an empty list; `_get` discards response headers, so `Retry-After`, GitHub's rate headers and Stack Exchange's `backoff` are never seen. | `lookups.py:76-83`, 131-132, 162-163, 422-425 | local-deep-research's per-engine wait learning; the sources' own rules |
| 6 | **SearXNG spends the Stack Exchange and GitHub quotas uncounted.** One `it` query fires three Stack Exchange engines (stackoverflow, askubuntu, superuser) and one GitHub engine, keyless, on the shared address. A stuck lookup asks Stack Exchange directly (2 requests) and then SearXNG (3 more). The model's own tool may search 8 times a stage visit. | `docker/searxng/settings.yml:16-21`; `lookups.py:271-273`; `research.py` `MOST_WEB_LOOKUPS = 8`; `DAILY_CAPS` counts only the direct calls | One counter per upstream |
| 7 | **Blocked engines are still configured and switched on.** Google, Startpage, Mojeek, Brave and Bing are kept and explicitly enabled; a general query waits on them for up to 10 s. Suspension times are not set. The response's `unresponsive_engines` list is not read. | `docker/searxng/settings.yml:9-14`, 62-73; `web_search.py:105` | Vane and Khoj rely on stock engines too, so this is a common weakness, not best practice |
| 8 | **Nothing is safe for concurrent runs.** The daily counter is read, changed and written back without a lock; the cache is one file per query on a local disk; two runs asking the same question both go upstream; registry and docs caches are per-process dictionaries. | `lookups.py:305-320`, 364-382; `package_registry.py:346`; `docs.py:84` | Morphic's Redis cache is the only shared cache read; HK.12 already plans the right design |
| 9 | **"Nothing found" is never remembered**, so a query with no answer is asked again by every run. | `lookups.py:437-438` | HK.3(h) plans a one-day memory |
| 10 | **robots.txt is fetched on every read, twice when a page redirects, and wildcard rules are not honoured.** Python's standard parser ignores `*` and `$` in paths, so GitHub's `Disallow: /*/tree/` is not applied (checked: it answers "allowed"). | `page_reader.py:187-200`, 366, 371 | RFC 9309 requires wildcard matching and allows caching for up to 24 hours |
| 11 | **Only accepted Stack Overflow answers, one site, cut to 600 characters; GitHub issues sorted by comment count, body only.** The fix is usually in a closing comment or a later, higher-voted answer. | `lookups.py:128-149`, 159-170, `MOST_EXCERPT = 600` | HK.3(c)-(e) already covers this |
| 12 | **The probe tests the reader on example.com**, which never fails the way real answer pages do. | `scripts/loop/lookup_ready.py` `PAGE` | Probe one page of each kind that matters |

Not a gap: `ddgs`, Jina Reader, Firecrawl and crawl4ai are absent. None would improve on the present design
(see (f)).

## (e) Implementation plan

Ranking is by expected effect on stuck defects being fixed, then by what production needs. "Fix" means always on
(a defect or a quality change, per the switch policy); "switch" means doubtful until measured. Every outward call in
every item goes through the HK.5 gate (`src/app/tools/outbound.py`, built). KS.1-KS.4 make one bundle with HK.3; KS.5-KS.6 are the first slice of HK.12.

### KS.1 Read each site through its official channel. Fix. Size M. Rank 1.

- **What.** A small router in front of `page_reader._text` (new module `src/app/tools/source_readers.py`, called
  from `page_reader.text_of` and `read`): an address is matched to a reader before any HTML is fetched.
  - `stackoverflow.com`, `*.stackexchange.com`, `superuser.com`, `askubuntu.com`, `serverfault.com` question
    addresses: Stack Exchange API, question plus answers with bodies, accepted first, then by votes, each with its
    date and score. Attribution (link and author) is kept, as the content licence requires.
  - `github.com/<owner>/<repo>/issues|pull/<n>`: REST issue plus comments; the closing comment and replies by
    maintainers (`author_association`) first; state and the linked fix.
  - `github.com/.../blob/<ref>/<path>`: the raw file host. `/releases`: the releases API. Repository root: the
    README API.
  - `www.npmjs.com/package/<name>`, `pypi.org/project/<name>`, `crates.io/crates/<name>`: the registry's own
    document through `package_registry` (the README or description), never the HTML page.
  - Any other host: first a Markdown variant when the server offers one (the reader already sends
    `Accept: text/markdown`, `page_reader.py:108`), then the present HTML path.
- **Merge.** This is the reader HK.3(d) needs ("read the resolution"); build it once here and have HK.3 call it.
  `lookups.stack_exchange` and `lookups.github_issues` then return leads only, and the reading is this module's.
- **Privacy.** Calls carry only a public id taken from a public address. The gate checks the address itself (path
  and query) for the product's private words before it is read.
- **Tests that fail on old code** (recorded responses, no network): a Stack Overflow question address returns the
  accepted answer's text (old: the 403 error); a GitHub issue address returns the closing comment (old: absent); a
  GitHub file address makes its request to the raw host (old: the HTML page).
- **Measure.** Share of `read_web_page` and lookup reads that return text, by host, before and after.

### KS.2 Keep code as code. Fix. Size S. Rank 2.

- **What.** `page_reader._MainText`: a `<pre>` becomes a fenced block, with the language from its class when there
  is one; inline `<code>` gets backticks. `lookups._plain` (`lookups.py:117-120`) keeps line breaks inside `<pre>`.
  Excerpts are cut at a block boundary, never inside a fence.
- **Why not swap in trafilatura.** Its benchmarks are for news articles and it has an open code-indentation bug.
  The present parser with `<main>`/`<article>` preference is the right shape; it needs fences, not replacing. Revisit
  only if KS.6 shows boilerplate dominating reads.
- **Tests that fail on old code:** an answer body with a three-line `<pre>` keeps three lines and a fence.
- **Measure.** The HK.4 replay set: does the note name the known fix more often.

### KS.3 Tell "refused" from "nothing found", and wait when told to. Fix. Size S-M. Rank 3.

- **What.** `lookups._get` returns headers as well. Each source reports one of: answered, nothing found, refused
  (status, and until when). Read Stack Exchange's `backoff` and `quota_remaining`, GitHub's `retry-after`,
  `x-ratelimit-remaining` and `x-ratelimit-reset`, and SearXNG's `unresponsive_engines`. A refused source is
  skipped until the stated time (a circuit breaker per source); with no stated time, exponential backoff with
  jitter, capped. The ledger line and the probe say "refused", not "0 found".
- **Design point for HK.3(h).** Only a true "nothing found" may be remembered for a day. A refusal must never be
  remembered as "nothing found".
- **Tests that fail on old code:** a 429 with `Retry-After` is recorded as refused and the source is not asked again
  inside the window (old: asked again, counted as nothing found); a Stack Exchange body with `backoff: 30` holds
  that source for 30 seconds.
- **Measure.** `loop.sh effects`: per source, answered / nothing found / refused / capped.

### KS.4 One search path, no double spending; drop the blocked engines. Fix. Size S. Rank 4.

- **What.**
  - `docker/searxng/settings.yml`: remove google, startpage, mojeek, brave and bing from `keep_only` and the
    `engines` block. Keep duckduckgo and wikipedia as the general pair. Set `suspended_times` explicitly.
  - Remove the three Stack Exchange engines and the GitHub engine from SearXNG. `web_search.search` then merges
    three things under one counter: the direct Stack Exchange search (keyed when a key exists, counted, with answer
    bodies), the direct GitHub issue search, and SearXNG for everything else (MDN, Microsoft Learn, registries,
    wikis, forums, DuckDuckGo).
  - GitHub issue search by best match, not by comment count, restricted to the library's own repository when the
    registry gives one (this part is HK.3(c); listed here so it is not built twice).
- **After the change:** deploy, then run the lookup probe, as the scaffold-check rule requires for configuration
  changes.
- **Tests that fail on old code:** the settings file names no engine from a "blocked" list kept in one place; one
  model search costs at most N Stack Exchange requests against the counter (old: three uncounted).
- **Measure.** Median search time; Stack Exchange `quota_remaining` at the end of a day's runs.

### KS.5 A shared cache, single-flight and atomic counters. Fix. Size M. Rank 5. First slice of HK.12.

- **What.** One module in front of every source (HK.12's "lookup service"), built now in its smallest useful form
  on the Redis and Postgres the stack already runs (`pyproject.toml:34`):
  - **Counters:** an atomic increment per source and day, replacing the read-change-write file
    (`lookups.py:305-320`).
  - **Token bucket per upstream**, shared by all runs, sized from the published limits: Stack Exchange 10,000 a day
    with a key and never the same request twice inside a minute; GitHub search 30 a minute with a token; crates.io
    1 a second; SearXNG a small fixed number in flight.
  - **Cache** keyed by source and normalised query, or by address for a page read. Lifetimes as HK.12 lists them,
    plus robots.txt per host for 24 hours and a read page for one hour (seven days for a versioned address such as
    a release or a commit-pinned file).
  - **Single-flight:** the first asker takes a short lock on the key; others wait for its answer and read the cache.
  - **Fallback:** when Redis is unreachable, the present file cache and a process lock, so a lookup never fails a
    stage.
- **Privacy.** Only an entry whose query passed the HK.5 gate as public is shared across tenants. The key never
  holds who asked. A tenant whose choice is "Off" neither reads nor writes.
- **Tests that fail on old code:** twenty threads counting at once give a total of twenty (old: fewer); two
  concurrent identical lookups make one upstream request; a second read of a page on the same host does not fetch
  robots.txt again.
- **Measure.** Cache hit rate; upstream requests per run; refusals per day.

### KS.6 A health probe that tests what matters. Fix. Size S. Rank 6.

- **What.** Extend `scripts/loop/lookup_ready.py` (still a warning, never a block):
  - one line per SearXNG engine that did not answer, from `unresponsive_engines`;
  - Stack Exchange `quota_remaining` and GitHub's `rate_limit` (that call does not count against the limit);
  - the reader probed on one address of each kind: a Stack Overflow question, a GitHub issue, a GitHub file, a
    documentation page, instead of example.com.
- **And in `loop.sh effects`:** answer rate per source; reads by outcome and host; the share of looked-up defects
  closed by the next fix (HK.4's measure).
- **Tests that fail on old code:** the probe output names an unresponsive engine given a recorded response that
  lists one.

### KS.7 Correct robots.txt matching. Fix. Size S. Rank 7.

- **What.** Replace the standard parser with one that honours `*` and `$` (RFC 9309), for example the
  [Protego](https://github.com/scrapy/protego) library that Scrapy uses, or a small matcher of our own. With KS.1,
  most disallowed GitHub paths are no longer read as HTML anyway.
- **Test that fails on old code:** `Disallow: /*/tree/` refuses `/a/b/tree/main`.

### KS.8 Decide the browser fallback on numbers. Switch (`PAGES_RENDERED_IN_A_BROWSER`), off. Size S-M. Rank 8.

- **What.** After KS.1 the two hosts seen answering 403 (Stack Overflow, npmjs) are read by API. KS.6 then counts
  how many reads still fail as "builds its text with scripts" or 403. If that share is material, add Python
  `playwright` to the worker image, reusing the Chromium already installed for product tests (`Dockerfile:208`),
  as one shared browser behind a small semaphore (Vane's pattern). If not, delete the dead path.
- **Concurrency.** A browser per page will not scale; one browser, a few pages at a time, a 20-second limit.

### KS.9 A local documentation tier for scale. Switch (`DOCS_READ_FROM_A_LOCAL_COPY`), off. Size M-L. Rank 9.

- **What.** For the stack's main libraries, answer documentation questions with no outward call: the installed
  package's own files first (HK.3(a) already plans this, and it is the cheapest "local index"), then a kept copy
  of each library's Markdown documentation fetched once per version, shared by all runs. A self-hosted DevDocs
  container is the ready-made alternative.
- **Why a switch.** It adds storage and a freshness question, and its value depends on how often `read_docs` is
  the bottleneck. Measure outward documentation requests per run first.

### KS.10 Keys for the two free APIs. Owner action, not built by me. Rank: do before production.

- A Stack Exchange application key and a GitHub token with no scopes raise the limits from 300 a day and 10
  searches a minute to 10,000 a day and 30 a minute. The admin page already takes both
  (`lookups.py:99-114`). Whether Stack Exchange key registration is still free is **unverified**; the owner
  would find out on registering.
- One paid general-web key with a hard daily cap stays HK.12's fallback (open point 4 of that report). Brave is no
  longer free, and its terms restrict storing results, which conflicts with a shared cache: check the plan's terms
  before caching its answers.

### How the items sit with HK.3, HK.5 and HK.12

| Item | Belongs with | Note |
|---|---|---|
| KS.1, KS.2 | HK.3(d) | The reader HK.3 calls; build once |
| KS.3 | HK.3(h), HK.12 breaker | Refusal is not "nothing found" |
| KS.4 | HK.3(c) | One search path; issue search by relevance is HK.3's |
| KS.5 | HK.12 | Its first slice; per-tenant budgets and the frozen snapshot stay in HK.12 |
| KS.6 | HK.4 | The probe and the effects lines |
| all | HK.5 | Every query and every address read passes the gate; only gate-passed entries are shared |

**Suggested order:** KS.1 + KS.2 + KS.3 + KS.4 with the HK.3 bundle (one subsystem, one deploy at a run boundary,
then the probe); KS.6 and KS.7 in the same bundle if there is room; KS.5 as the next bundle; KS.8 and KS.9 only
after KS.6's numbers.

**How to judge the whole:** the HK.4 replay set (does the note name the known fix), and on live runs the share of
looked-up defects closed by the next fix (2 of 9 today, per HK.3). If KS.1-KS.4 do not move either, the search
path was not the limit and effort goes to HK.3's query building and condensing instead.

## (f) What not to do

- **Do not scrape Google, Bing or DuckDuckGo result pages directly, and do not add `ddgs`.** It is the same
  scraping SearXNG already does, with a history of breaking, and against the engines' terms.
- **Do not use Tor, rotating or residential proxies, CAPTCHA solvers or browser-fingerprint tricks** to get past a
  block. That is circumvention, the conduct at issue in Google v. SerpApi, and it gets an address range banned.
- **Do not point the harness at public SearXNG instances.** They rate-limit API use (4 non-HTML requests an hour
  per address with the limiter on) and it moves the load onto volunteers.
- **Do not add more SearXNG instances for capacity.** The limit is the upstream's view of one address; cache instead.
- **Do not fetch Stack Overflow or GitHub HTML when an API exists**, and do not ignore robots.txt to do so.
- **Do not send addresses or queries to a hosted reader or keyless vendor endpoint** (Jina Reader, You.com, Exa) by
  default. They are third parties outside the HK.5 gate's control, and their free terms change without notice.
- **Do not build an index from Stack Exchange data dumps** without reading their current access terms.
- **Do not cache or share a paid provider's results** before checking its storage terms.
- **Do not remember a refusal as "nothing found"**, and do not retry a refused source before the time it gave.
- **Do not put a contact detail of a tenant in a User-Agent.** Where a source asks for an identifying User-Agent
  (Wikimedia, crates.io), use one deployment-level contact the owner sets.

## Not verified, and limits of this research

- Jan was read from documentation only. Open Interpreter and OpenHands were read at release tags because their
  default branches have been restructured.
- Free tiers of Tavily, Exa and Serper; deps.dev limits; whether a Stack Exchange key is still free; the current
  state of Google v. SerpApi.
- The page-reader checks in (d) were run on the host's project environment, not inside the worker container; the
  worker's image is built from the same `pyproject.toml`, which does not list `playwright`.
- SearXNG engine health was taken from upstream issues and this harness's own measurement of 2026-11-20, not
  re-measured (the brief excluded touching the containers).
- Two sub-agents' live checks used one anonymous Stack Exchange request and three anonymous GitHub requests from
  this machine's address; my own checks fetched six public pages and three robots.txt files.
