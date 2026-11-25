# Failed runs overnight 11-25/26 (all harness faults, all fixed)

| Run | Family | Failed | Cause | Fix |
|---|---|---|---|---|
| run-32362f3b (Medium 4) | medium brief, thorough | 23:43 JST, sprint 1 attempt 2, 9 of 21 | fixers without the error (no error line in eight briefs; the server log kept access lines; reads folded; the lead re-planned from test names) | FX.1-FX.11 (LF.1410-1427) and the deep-review fixes (LF.1430-1497) |
| run-038f60eb | web-todo-react 6 | 02:07 JST, intake | `model_unavailable` while the host swapped and olla marked both instances unhealthy | LF.1438: outages waited for up to 10 minutes |
| run-a2f91f9f | web-todo-react 7 | 03:11 JST, first fix round | screenshots sent to a model without a vision part (500 "image input is not supported"); the capability came from the model card | LF.1495-1497; runtime `model_reads_images=no` meanwhile |
| run-03668d05 | notes-api-go 14 | 08:02 JST, testing builder | a command printed byte 0xb9; the sandbox decoded output as strict UTF-8 and `UnicodeDecodeError` ended the run | LF.1498: every harness `subprocess` text read uses `errors="replace"` |

Delivered in the same window: notes-api-php 8 (9/9, 8/8) and fullstack-bookmarks 16 (8/8).
