"""An HTTP service in TypeScript on Hono, run by Node itself: no compiler step, no Jest, no ts-jest.

A measured arm of `node-hono-api` for weaker models (behind `HONO_NATIVE_TEST_RUNNER`, owner 2026-10-25). Five runs of a
small model on the Jest pack ended with a product that did not build: ts-jest, a build step and Jest's own
configuration were each a way to fail beyond the model's own code. Node 24 runs `.ts` files as they are (it strips the
types), so the service starts with `node src/main.ts`, the unit tests are Node's own `node:test`, and `tsc --noEmit`
is only a check. The price is a narrower TypeScript: only syntax that is types and nothing else (no enums, no
namespaces, no parameter properties), and relative imports that name the `.ts` file.
"""

from __future__ import annotations

from app.stacks.packs import _javascript as js
from app.stacks.packs._service import service_pack
from app.switches import is_on

#: Off in code like every switch; the compose file decides whether the arm runs (`app.stacks.choose_pack`).
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("HONO_NATIVE_TEST_RUNNER", ON_BY_DEFAULT)


UNIT_FILES = "'test/**/*.test.ts'"

UNIT_SCRIPT = (
    "mkdir -p test-results && node --test --test-reporter=spec --test-reporter-destination=stdout "
    f"--test-reporter=junit --test-reporter-destination=test-results/unit.xml {UNIT_FILES}"
)

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node src/main.ts",
    "typecheck": "tsc --noEmit",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "@hono/node-server": "^1.13.0",
    "hono": "^4.6.0"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "@types/node": "^22.0.0",
    "typescript": "^5.8.0"
  }
}
""" % {"unit": UNIT_SCRIPT.replace('"', '\\"'), "playwright": js.PLAYWRIGHT}

TSCONFIG = """{
  "compilerOptions": {
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "target": "ES2022",
    "strict": true,
    "noEmit": true,
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "erasableSyntaxOnly": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["src", "test"]
}
"""

APP = """import { Hono } from 'hono';

// Builds the service. `src/main.ts` serves it; unit tests call `app.request(...)` on it directly.
export function createApp(): Hono {
  const app = new Hono();

  app.get('/health', (c) => c.json({ status: 'ok' }));

  return app;
}
"""

MAIN = """import { serve } from '@hono/node-server';
import { createApp } from './app.ts';

const port = Number(process.env.PORT || 3000);
const hostname = process.env.HOST || '127.0.0.1';

serve({ fetch: createApp().fetch, port, hostname }, () => {
  console.log(`Listening on http://${hostname}:${port}`);
});
"""

SMOKE_UNIT = """import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createApp } from '../src/app.ts';

test('the service reports its health', async () => {
  const response = await createApp().request('/health');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: 'ok' });
});
"""

GUIDE = """The service is Hono in TypeScript, run by Node itself: `src/main.ts` serves `createApp()` from `src/app.ts` and
`npm start` is `node src/main.ts` - there is no build step and no compiler output. Because Node strips the types and
runs the file, write only TypeScript that is types and nothing else: type annotations, `interface`, `type`, `import
type`; NOT `enum`, `namespace`, class parameter properties (`constructor(private x: T)`) or decorators. Import your own
files with their extension, `import { x } from './x.ts'`, and packages by name. Add routes to the application
(`app.get('/items', (c) => c.json(items))`, `app.post(...)`, a `Hono` per area mounted with `app.route('/items',
itemsApp)`); read a JSON body with `await c.req.json()` and answer with `c.json(body, status)`.
Unit tests go in `test/`, named `<area>.test.ts`, with Node's own runner: `import { test } from 'node:test'`,
`import assert from 'node:assert/strict'`, and call the application in memory - `await createApp().request('/items',
{ method: 'POST', body: JSON.stringify({ ... }), headers: { 'content-type': 'application/json' } })` returns a standard
`Response`. Use that, not a client library: `hono/testing` exports only `testClient`, which needs the route types, and
nothing else (no `createClient`, no `createTestClient`). Before you finish, run `npm run typecheck` (it only checks;
it writes nothing) and `npm test`. Install a dependency with `npm install <name>`; look up what a package exports with
the `module_exports` tool before importing a name you are not sure of."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 3000:3000 -v {{project}}-data:/data {{project}}`.
FROM node:%(node)s-slim
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 DATA_DIR=/data
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
RUN mkdir -p /data && chown node:node /data
USER node
EXPOSE 3000
CMD ["node", "src/main.ts"]
""" % {"node": js.NODE_MAJOR}

PACK = service_pack(
    name="node-hono-native-api",
    entrypoint="src/app.ts",
    required_exports={"src/app.ts": ("createApp",)},
    relative_import_extension=".ts",
    typecheck=("npm", "run", "typecheck"),
    title="HTTP service in TypeScript on Hono, run by Node",
    language="typescript",
    frameworks=("hono",),
    files={
        "package.json": PACKAGE_JSON,
        "tsconfig.json": TSCONFIG,
        "src/app.ts": APP,
        "src/main.ts": MAIN,
    },
    install=(),
    unit_test=js.UNIT_TEST,
    unit_report="test-results/unit.xml",
    unit_dir="test",
    unit_pattern="*.test.ts",
    start="exec node src/main.ts",
    server_timeout_ms=60_000,
    smoke_unit=("test/scaffold-smoke.test.ts", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "Hono",
        "frontend_framework": "",
        "testing_framework": "node:test for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": js.DOCKERIGNORE},
    kept_scripts={"test": UNIT_SCRIPT, "start": "node src/main.ts"},
    # The server's bootstrap is the pack's: it serves `createApp()` on `HOST` and `PORT`. Three small-model runs rewrote
    # it (a host of `127.0.0-1`, a call to a `startServer` of its own, an import of a module that was not there) and
    # the product did not start for the first half hour; the application is what the team writes, in `src/app.ts`.
    # `tsconfig.json` is kept for the same reason: a run changed its `module` setting and `tsc` then reported only the
    # configuration, so no compiler error reached the fixers.
    kept_files=("src/main.ts", "tsconfig.json"),
)
