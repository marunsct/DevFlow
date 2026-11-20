# Reports

Every report written about the product or its runs lives here as a Markdown file in the repository - never in a cloud
document - so it is easy to find, diff and keep. The live status is not a report: it is `docs/STATE.md`.

| Folder | What goes in it | Naming |
|---|---|---|
| `audits/` | Audits of the harness: per-role audits, deep reviews, efficiency audits | `YYYY-MM-DD-<slug>.md` |
| `product-reviews/` | The end-of-run product review: features to improve, how other harnesses do it, the value added | `YYYY-MM-<slug>.md` (or one file per run: `YYYY-MM-DD-<family>-container-N.md`) |
| `research/` | Research on how others do something, with sources | `YYYY-MM-DD-<slug>.md` |
| `status-board/` | The archived history of the former cloud status board | read-only history |

Rules: one file per report, dated, committed in the commit that writes it; cite sources as links; times in JST; no secrets.
