# DevFlow

DevFlow builds a small software product from a written brief. Agents running on a language model you provide plan
the work in sprints, write the code and its tests, write and lock an acceptance suite from the brief, fix what fails,
and hand you the product with a record of what was proven and what was not.

**What it is good at today:** small, well-specified, single-service products in Python or JavaScript/TypeScript - an
HTTP API, a command-line tool, a library, a browser page, a page with its own API - with a local model of about
the size of Qwen3.6-35B. Larger briefs, other languages and other models work less reliably and are labelled
experimental. A run takes one to three hours on such a model.

## Quick start

You need Docker with Compose, about 20 GB of disk, and a model server that speaks the OpenAI chat API (LM Studio,
llama.cpp's server, vLLM, or a hosted provider). DevFlow never downloads or starts a model for you.

```sh
git clone <this repository> devflow && cd devflow
scripts/setup-env.sh            # writes .env with fresh secrets and prints the admin password
docker compose up -d --build    # starts the app, the worker, Postgres and Redis
```

Open <http://localhost:8000> and sign in as `admin` with the password `setup-env.sh` printed (it is also
`ADMIN_PASSWORD` in `.env`).

### Connect a model

In **Settings > Models**, enter the address of your model server (for a server on the same machine, use
`http://host.docker.internal:<port>/v1`), its key if it has one, and the model's name; press **Detect** to read its
context window, then **Diagnose this model and set its guidance** - a few minutes of checks that decide how the agents are steered for it.
A model with a context window of at least 64k tokens per request is recommended.

### Allow commands

The agents install packages and run tests inside the worker. That is off until you allow it in `.env`:

```sh
ALLOW_COMMAND_EXECUTION=true
SANDBOX_EXECUTION_MODE=container   # each command in its own container (needs the Docker socket), or in-container
```

`in-container` runs commands in the worker itself: use it only on a machine where you are the only user.

## Running it for other people

`docker compose up` as above is for one person on their own machine. To serve it to others:

```sh
SITE_ADDRESS=devflow.example.com docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

This runs in production mode (missing or published secrets stop the server; the API pages are off) and puts the app
behind Caddy on ports 80 and 443 with TLS and security headers; the app itself is no longer published. Keep machine-only
changes (an extra port, a volume) in `docker-compose.override.yml`, which Compose reads automatically and git ignores.

### When several people share one deployment

By default an agent's command runs inside the worker. That is fine on your own machine, but on a shared deployment add
the sandbox file, so each command runs in a container of its own - no network unless it installs, no capabilities, a
read-only root, only its run's workspace, none of the server's secrets:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.sandbox.yml up -d
```

The worker reaches Docker only through a proxy that allows running containers. The first commands pull the toolchain
images (Node with browsers, Python, Go, Rust), which takes a few minutes once.

## Your first run

1. On **Home**, write the brief: what the product does, its features as a list, and - if you know them - its
   interface (routes, commands, what a page shows) and technical constraints. The preview shows the acceptance
   criteria the run will be held to; tighten any it marks as vague.
2. Choose how involved you want to be. **Hands-off** runs to the end on its own; the reviews pause the run for you at
   the points you tick, and a browser notification tells you when it waits.
3. Start it, and follow it on the run page: the stage now, the sprint, the tests passing, and what it is fixing.
4. When it finishes, read the verdict - **Delivered**, **Delivered with cuts** (criteria shipped without proof,
   listed), or **Not deliverable** (a gap that means it may not work, listed) - then **Download product**. The
   archive holds the code with its git history and a `HOW-TO-RUN.txt`; the run page shows the same commands.

## When something goes wrong

A failed or paused run can be resumed from its last completed stage, rewound to an earlier one, or cloned. The run
page says what stopped it. A run that needs you waits; nothing is lost by leaving it.

## More

- [docs/README.md](docs/README.md) - the map of the documentation; [docs/PRODUCT.md](docs/PRODUCT.md) - how it works and is built, completely; [docs/STATE.md](docs/STATE.md) - where it stands now.
- [.env.example](.env.example) - every setting, with what it does.
- [docs/HANDOVER.md](docs/HANDOVER.md) - for the people operating and improving the harness.
