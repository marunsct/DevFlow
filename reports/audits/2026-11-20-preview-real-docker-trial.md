# Product preview: real-Docker trials (2026-11-20)

Target: a finished web-todo run (browser JavaScript pack), container mode, the preview switch turned on only inside the one process that started each preview.

## Trial 1 (13:40 JST, harness at 868e87ac)
- The app refused to start a preview: it read its own execution mode, which only the worker carries (the sandbox overlay sets container mode for the worker alone).
- Past that check (patched in that one process), the worker copied sprint 1, started its container on `devflow-preview` and the product served - on `127.0.0.1` inside its container, so the app's connection was refused. The browser pack's own serve template hard-coded `127.0.0.1`.
- Stop worked: the state read "stopped" and the container was gone within 12 s.
- Fixed in LF.1184: a worker heartbeat (its own thread, every 5 s) is what the app checks; a Node forwarder in the preview container serves the preview port on every interface; the browser pack listens on `HOST`.

## Trial 2 (14:06 JST, harness at 5431331b)
- Heartbeat present (`contained: true`); the start was accepted with no patch.
- Ready within about 20 s; the app fetched the page through the forwarder: 200, "Simple To-Do List App".
- The container: network `devflow-preview` only, read-only root, all capabilities dropped, 4 GB memory cap.
- From inside it, Redis, the database, the worker, example.com and 1.1.1.1 were all unreachable.
- Stop removed the container within 12 s.
- The browser pack scaffolds after the template change (`verify_packs browser-javascript`: ok in 14 s).

## Not yet exercised
- The token-gated HTTP proxy route and the run page's frame end to end (the app's serving processes still have the switch off), and point and say on a live page.
- A service product (request console) and a stack whose image has no Node.

## Next
Turn `PRODUCT_PREVIEW` on for a short supervised trial through the run page on a finished run, then decide whether it goes on by default.
