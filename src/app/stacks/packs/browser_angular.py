"""A page that runs in a browser, built with Angular and TypeScript.

The files are the ones the Angular CLI generates for a new application -
standalone components, no zone.js, Vitest through `ng test` - cut to what a
product starts from. Angular 22 needs Node 22.22 or later; the image runs
`_javascript.NODE_MAJOR`.
"""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js
from app.stacks.packs import browser_vue as vue
from app.stacks.packs._fullstack import STYLES

ANGULAR = "^22.2.0"

#: `ng test` runs Vitest in a simulated DOM; `--output-file` belongs to the
#: first reporter, so JUnit comes first and the console report second.
UNIT_SCRIPT = (
    "ng test --no-watch --reporters=junit --reporters=default --output-file=test-results/unit.xml"
)

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "ng": "ng",
    "start": "ng serve",
    "build": "ng build",
    "test": "%(unit)s",
    "test:acceptance": "playwright test"
  },
  "dependencies": {
    "@angular/common": "%(angular)s",
    "@angular/compiler": "%(angular)s",
    "@angular/core": "%(angular)s",
    "@angular/forms": "%(angular)s",
    "@angular/platform-browser": "%(angular)s",
    "@angular/router": "%(angular)s",
    "rxjs": "~7.8.0",
    "tslib": "^2.3.0"
  },
  "devDependencies": {
    "@angular/build": "%(angular)s",
    "@angular/cli": "%(angular)s",
    "@angular/compiler-cli": "%(angular)s",
    "@playwright/test": "%(playwright)s",
    "axe-core": "%(axe)s",
    "jsdom": "^30.0.0",
    "typescript": "~6.0.2",
    "vitest": "^5.0.0"
  }
}
""" % {"unit": UNIT_SCRIPT, "angular": ANGULAR, "playwright": js.PLAYWRIGHT, "axe": js.AXE_CORE}

ANGULAR_JSON = """{
  "$schema": "./node_modules/@angular/cli/lib/config/schema.json",
  "version": 1,
  "cli": {
    "packageManager": "npm",
    "analytics": false
  },
  "newProjectRoot": "projects",
  "projects": {
    "{{project}}": {
      "projectType": "application",
      "schematics": {},
      "root": "",
      "sourceRoot": "src",
      "prefix": "app",
      "architect": {
        "build": {
          "builder": "@angular/build:application",
          "options": {
            "browser": "src/main.ts",
            "tsConfig": "tsconfig.app.json",
            "assets": [{ "glob": "**/*", "input": "public" }],
            "styles": ["src/styles.css"]
          },
          "configurations": {
            "production": {
              "budgets": [
                { "type": "initial", "maximumWarning": "1MB", "maximumError": "2MB" },
                { "type": "anyComponentStyle", "maximumWarning": "8kB", "maximumError": "16kB" }
              ],
              "outputHashing": "all"
            },
            "development": {
              "optimization": false,
              "extractLicenses": false,
              "sourceMap": true
            }
          },
          "defaultConfiguration": "production"
        },
        "serve": {
          "builder": "@angular/build:dev-server",
          "configurations": {
            "production": { "buildTarget": "{{project}}:build:production" },
            "development": { "buildTarget": "{{project}}:build:development" }
          },
          "defaultConfiguration": "development"
        },
        "test": {
          "builder": "@angular/build:unit-test"
        }
      }
    }
  }
}
"""

TSCONFIG = """{
  "compileOnSave": false,
  "compilerOptions": {
    "strict": true,
    "noImplicitOverride": true,
    "noPropertyAccessFromIndexSignature": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "experimentalDecorators": true,
    "importHelpers": true,
    "target": "ES2022",
    "module": "preserve"
  },
  "angularCompilerOptions": {
    "enableI18nLegacyMessageIdFormat": false,
    "strictInjectionParameters": true,
    "strictInputAccessModifiers": true,
    "strictTemplates": true
  },
  "files": [],
  "references": [{ "path": "./tsconfig.app.json" }, { "path": "./tsconfig.spec.json" }]
}
"""

TSCONFIG_APP = """{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "types": []
  },
  "include": ["src/**/*.ts"],
  "exclude": ["src/**/*.spec.ts"]
}
"""

TSCONFIG_SPEC = """{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "types": ["vitest/globals"]
  },
  "include": ["src/**/*.d.ts", "src/**/*.spec.ts"]
}
"""

INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{title}}</title>
  <base href="/">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
  <app-root></app-root>
</body>
</html>
"""

MAIN = """import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
"""

APP = """import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
"""

APP_HTML = """<main>
  <h1>{{title}}</h1>
  <router-outlet />
</main>
"""

APP_CONFIG = """import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [provideBrowserGlobalErrorListeners(), provideRouter(routes)],
};
"""

ROUTES = """import { Routes } from '@angular/router';

export const routes: Routes = [];
"""

SMOKE_UNIT = """import { TestBed } from '@angular/core/testing';
import { App } from './app';

describe('App', () => {
  it('renders its heading', async () => {
    await TestBed.configureTestingModule({ imports: [App] }).compileComponents();
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).querySelector('h1')).not.toBeNull();
  });
});
"""

GUIDE = """The page is an Angular application in TypeScript, built from standalone
components in `src/app/`: `app.ts` is the root component, `app.html` its template,
`app.config.ts` its providers and `app.routes.ts` its routes. Each component is a
`<name>.ts` with its own `<name>.html` and `<name>.css`, listed in the `imports` of
the components that use it; hold state in signals (`signal`, `computed`). Create
one with `npx ng generate component <name>`. Unit tests sit beside what they test,
named `<name>.spec.ts`, using Angular's `TestBed` with Vitest (`describe`, `it` and
`expect` are globals) in a simulated DOM. Run them with `npm test`. Install a
dependency with `npm install <name>` (`--save-dev` for one only tests use). Never
start a server yourself."""

PACK = StackPack(
    name="browser-angular",
    title="Browser app in Angular and TypeScript",
    kind="browser_app",
    language="typescript",
    frameworks=("angular",),
    frontend_frameworks=("angular",),
    files={
        "package.json": PACKAGE_JSON,
        "angular.json": ANGULAR_JSON,
        "tsconfig.json": TSCONFIG,
        "tsconfig.app.json": TSCONFIG_APP,
        "tsconfig.spec.json": TSCONFIG_SPEC,
        "playwright.config.js": js.playwright_config(
            "node_modules/.bin/ng serve --host 127.0.0.1 --port ${port}", "/", screenshot="on",
            checks_the_page=True, server_timeout_ms=120_000,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        "public/.gitkeep": "",
        "src/index.html": INDEX,
        "src/main.ts": MAIN,
        "src/styles.css": STYLES,
        "src/app/app.ts": APP,
        "src/app/app.html": APP_HTML,
        "src/app/app.css": "",
        "src/app/app.config.ts": APP_CONFIG,
        "src/app/app.routes.ts": ROUTES,
        ".gitignore": js.GITIGNORE + "dist/\n.angular/\n",
    },
    install=js.INSTALL,
    unit_test=js.UNIT_TEST,
    acceptance_test=js.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="src",
    acceptance_dir="acceptance",
    acceptance_pattern="*.spec.js",
    unit_pattern="*.spec.ts",
    kept_files=("playwright.config.js", "playwright.setup.mjs"),
    unit_dom="Vitest's `jsdom` environment, which `ng test` sets up",
    kept_scripts={"test": UNIT_SCRIPT, "test:acceptance": "playwright test"},
    smoke_files={
        "src/app/scaffold-smoke.spec.ts": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": vue.SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=vue.ACCEPTANCE_GUIDE,
    stack={
        "language": "TypeScript",
        "framework": "Angular",
        "frontend_framework": "Angular",
        "testing_framework": "Vitest with Angular's TestBed (ng test) for unit tests, Playwright for acceptance tests",
    },
    check_families=frozenset({"javascript", "browser", "typescript"}),
    evidence_dir="test-results/evidence",
    test_bugs=js.TEST_BUGS,
    runtime_report=js.PAGE_LOAD_REPORT,
    locators_nobody_sees=js.LOCATORS_NOBODY_SEES,
    locators_that_do_not_exist=js.LOCATORS_THAT_DO_NOT_EXIST,
    locators_that_pick_one=js.LOCATORS_THAT_PICK_ONE,
    locators_by_a_missing_name=js.LOCATORS_BY_A_NAME_THE_ROLE_NEVER_HAS,
    finds_by_name=js.FINDS_BY_NAME,
    contradicting_locators=js.asserted_without_the_text_it_is_found_by,
    locator_left_behind=js.a_locator_left_behind,
    opens_no_page=js.tests_that_never_open_the_page,
    storage_before_page_open=js.storage_before_page_open,
    module_system_mismatch=js.module_system_mismatch,
    unawaited_helpers=js.unawaited_helpers,
    locators_with_an_ignored_option=js.locators_with_a_name_option,
    expects_what_it_never_gave=js.expects_what_it_never_gave,
    positions_it_asserts=js.positions_it_asserts,
    filtered_by_a_field_value=js.a_locator_filtered_by_a_field_value,
    failure_pages=js.failure_pages,
    near_misses=js.near_misses,
    needs_what_it_never_made=js.needs_what_it_never_made,
    assertion_names=js.playwright_assertions,
    code_runs_in="browser",
    ci_setup=js.CI_SETUP,
    ci_prepare=js.CI_BROWSERS,
    # Measured in the candidate image through the sandbox: `ng test` stopped
    # at "Failed to reserve virtual memory for CodeRange" under a 1 and a 1.5
    # GB data limit and ran out of heap at 2 GB; `ng serve`, started by the
    # acceptance suite, needed 4 GB - while the unit run used 439 MB at most
    # in one process, and the acceptance run with its browser 1.6 GB in all.
    # The limit counts reservations; the tree watcher counts use.
    process_memory="4g",
)
