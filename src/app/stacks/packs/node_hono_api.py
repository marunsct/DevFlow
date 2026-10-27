"""An HTTP service in TypeScript, on Hono."""

from __future__ import annotations

from app.stacks.packs import _javascript as js
from app.stacks.packs._service import FACTORY_GUIDE, service_pack

UNIT_SCRIPT = "jest --ci --reporters=default --reporters=jest-junit"

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "build": "tsc -p tsconfig.build.json",
    "start": "node dist/main.js",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "@hono/node-server": "^1.13.0",
    "hono": "^4.6.0"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "@types/jest": "^29.5.14",
    "@types/node": "^22.0.0",
    "jest": "^29.7.0",
    "jest-junit": "^16.0.0",
    "ts-jest": "^29.2.5",
    "typescript": "^5.6.0"
  },
  "jest": {
    "testEnvironment": "node",
    "roots": ["<rootDir>/test"],
    "testRegex": ".*\\\\.spec\\\\.ts$",
    "transform": { "^.+\\\\.ts$": "ts-jest" },
    "moduleFileExtensions": ["ts", "js", "json"]
  },
  "jest-junit": {
    "outputDirectory": "test-results",
    "outputName": "unit.xml"
  }
}
""" % {"unit": UNIT_SCRIPT, "playwright": js.PLAYWRIGHT}

TSCONFIG = """{
  "compilerOptions": {
    "module": "node16",
    "moduleResolution": "node16",
    "target": "ES2022",
    "outDir": "./dist",
    "rootDir": ".",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "types": ["node", "jest"]
  },
  "include": ["src", "test"]
}
"""

TSCONFIG_BUILD = """{
  "extends": "./tsconfig.json",
  "compilerOptions": { "rootDir": "./src", "types": ["node"] },
  "include": ["src"]
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
import { createApp } from './app';

const port = Number(process.env.PORT || 3000);
const hostname = process.env.HOST || '127.0.0.1';

serve({ fetch: createApp().fetch, port, hostname }, () => {
  console.log(`Listening on http://${hostname}:${port}`);
});
"""

SMOKE_UNIT = """import { createApp } from '../src/app';

describe('the service', () => {
  it('reports its health', async () => {
    const response = await createApp().request('/health');
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: 'ok' });
  });
});
"""

GUIDE = """The service is Hono in TypeScript: `createApp()` in `src/app.ts` builds the `Hono` application and
`src/main.ts` serves it with `@hono/node-server`. Add routes to the application
(`app.get('/items', (c) => c.json(items))`, `app.post(...)`, an area's routes as their own `new Hono()` - there is no `Router` - mounted with
`app.route('/items', itemsApp)`); read a JSON body with `await c.req.json()` and
return the answer the context builds - `return c.json(body, status)`: a handler that calls it without `return`, or is typed `void`, answers nothing, and every request then fails inside the server with `res.body.getReader is not a function`. Unit tests go in `test/`, named `<area>.spec.ts`, using Jest: Hono needs no
server for them, `await createApp().request('/items', { method: 'POST', body: JSON.stringify({ ... }),
headers: { 'content-type': 'application/json' } })` returns a standard `Response`. Use that, not a
client library: `hono/testing` exports only `testClient`, which needs the route types, and nothing else
(no `createClient`, no `createTestClient`). Run them with `npm test`; build with `npm run build`. Import a
file of your own without an extension (`import { x } from './x'`). Install a dependency with
`npm install <name>` (`--save-dev` for one only tests use)."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 3000:3000 -v {{project}}-data:/data {{project}}`.
FROM node:%(node)s-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:%(node)s-slim
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 DATA_DIR=/data
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
RUN mkdir -p /data && chown node:node /data
USER node
EXPOSE 3000
CMD ["node", "dist/main.js"]
""" % {"node": js.NODE_MAJOR}

PACK = service_pack(
    name="node-hono-api",
    entrypoint="src/app.ts",
    required_exports={"src/app.ts": ("createApp",)},
    title="HTTP service in TypeScript on Hono",
    language="typescript",
    frameworks=("hono",),
    files={
        "package.json": PACKAGE_JSON,
        "tsconfig.json": TSCONFIG,
        "tsconfig.build.json": TSCONFIG_BUILD,
        "src/app.ts": APP,
        "src/main.ts": MAIN,
    },
    install=(),
    unit_test=js.UNIT_TEST,
    unit_report="test-results/unit.xml",
    unit_dir="test",
    unit_pattern="*.spec.ts",
    start="npm run build && exec node dist/main.js",
    server_timeout_ms=120_000,
    smoke_unit=("test/scaffold-smoke.spec.ts", SMOKE_UNIT),
    guide=f"{GUIDE}\n{FACTORY_GUIDE}",
    stack={
        "language": "TypeScript",
        "framework": "Hono",
        "frontend_framework": "",
        "testing_framework": "Jest with ts-jest for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": js.DOCKERIGNORE + "dist/\n"},
    gitignore="dist/\n",
    kept_scripts={"test": UNIT_SCRIPT},
)
