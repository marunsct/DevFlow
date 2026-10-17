"""An HTTP service in TypeScript, on NestJS."""

from __future__ import annotations

from app.stacks.packs import _javascript as js
from app.stacks.packs._service import service_pack

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
    "@nestjs/common": "^11.0.0",
    "@nestjs/core": "^11.0.0",
    "@nestjs/platform-express": "^11.0.0",
    "reflect-metadata": "^0.2.2",
    "rxjs": "^7.8.1"
  },
  "devDependencies": {
    "@nestjs/testing": "^11.0.0",
    "@playwright/test": "%(playwright)s",
    "@types/jest": "^29.5.14",
    "@types/node": "^22.0.0",
    "jest": "^29.7.0",
    "jest-junit": "^16.0.0",
    "supertest": "^7.0.0",
    "@types/supertest": "^6.0.2",
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
    "module": "commonjs",
    "target": "ES2022",
    "declaration": false,
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true,
    "sourceMap": true,
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
  "compilerOptions": { "rootDir": "./src" },
  "include": ["src"]
}
"""

MAIN = """import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  const host = process.env.HOST || '127.0.0.1';
  const port = Number(process.env.PORT || 3000);
  await app.listen(port, host);
  console.log(`Listening on http://${host}:${port}`);
}

bootstrap();
"""

MODULE = """import { Module } from '@nestjs/common';
import { HealthController } from './health.controller';

// The service's module: add controllers and providers here as it grows.
@Module({
  controllers: [HealthController],
})
export class AppModule {}
"""

HEALTH = """import { Controller, Get } from '@nestjs/common';

@Controller('health')
export class HealthController {
  @Get()
  health() {
    return { status: 'ok' };
  }
}
"""

SMOKE_UNIT = """import { Test } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module';

describe('the service', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = moduleRef.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('reports its health', async () => {
    await request(app.getHttpServer()).get('/health').expect(200, { status: 'ok' });
  });
});
"""

GUIDE = """The service is NestJS in TypeScript: `src/main.ts` starts it, `src/app.module.ts`
lists its controllers and providers, and each area of the interface is a controller
(`@Controller('items')` with `@Get()`, `@Post()` ...) beside a provider that holds its
logic. Unit tests go in `test/`, named `<area>.spec.ts`, using Jest with
`@nestjs/testing` (`Test.createTestingModule`) and `supertest` to call the
application in memory. Run them with `npm test`; build with `npm run build`. Install a
dependency with `npm install <name>` (`--save-dev` for one only tests use)."""

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
    name="node-nest-api",
    entrypoint="src/app.module.ts",
    title="HTTP service in TypeScript on NestJS",
    language="typescript",
    frameworks=("nest", "nestjs", "nest.js"),
    files={
        "package.json": PACKAGE_JSON,
        "tsconfig.json": TSCONFIG,
        "tsconfig.build.json": TSCONFIG_BUILD,
        "src/main.ts": MAIN,
        "src/app.module.ts": MODULE,
        "src/health.controller.ts": HEALTH,
    },
    install=(),
    unit_test=js.UNIT_TEST,
    unit_report="test-results/unit.xml",
    unit_dir="test",
    unit_pattern="*.spec.ts",
    start="npm run build && exec node dist/main.js",
    server_timeout_ms=120_000,
    smoke_unit=("test/scaffold-smoke.spec.ts", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "NestJS",
        "frontend_framework": "",
        "testing_framework": "Jest with @nestjs/testing for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": js.DOCKERIGNORE + "dist/\n"},
    gitignore="dist/\n",
    kept_scripts={"test": UNIT_SCRIPT},
)
