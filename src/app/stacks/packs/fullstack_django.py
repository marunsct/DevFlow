"""Pages rendered by Django from templates, with the product's own JSON endpoints beside them."""

from __future__ import annotations

from app.stacks.packs._design import DESIGN_TOKENS

from app.stacks import StackPack
from app.stacks.packs import _javascript as js
from app.stacks.packs import _python

REQUIREMENTS = """django>=5.1
gunicorn>=23
whitenoise>=6.8
"""

REQUIREMENTS_DEV = """pytest>=8
pytest-django>=4.9
"""

MANAGE = '''#!/usr/bin/env python
"""Django's command-line utility for this project."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{{package}}.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
'''

SETTINGS = '''"""Settings, read from the environment where a deployment differs from a developer's machine.

`DATA_DIR` holds the database (a file, unless the deployment sets a server's in
`DATABASES`); `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` are
what a deployment sets.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
# A development default only: every deployment sets its own.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-development-only")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "{{package}}",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "{{package}}.urls"
WSGI_APPLICATION = "{{package}}.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
'''

URLS = '''"""Where each address goes: the pages, and the JSON endpoints under /api/."""

from django.urls import path

from {{package}} import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health", views.health, name="health"),
]
'''

VIEWS = '''"""The views: pages rendered from templates, JSON endpoints for scripts and clients."""

from django.http import JsonResponse
from django.shortcuts import render


def home(request):
    return render(request, "{{package}}/home.html")


def health(request):
    return JsonResponse({"status": "ok"})
'''

WSGI = '''"""What a server runs: `gunicorn {{package}}.wsgi`."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{{package}}.settings")
application = get_wsgi_application()
'''

HOME = """{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{title}}</title>
  <link rel="stylesheet" href="{% static '{{package}}/styles.css' %}">
</head>
<body>
  <main>
    <h1>{{title}}</h1>
  </main>
  <script type="module" src="{% static '{{package}}/main.js' %}"></script>
</body>
</html>
"""

MAIN_JS = """// The page's script: index of what the page does in the browser. Reach the
// service with fetch('/api/...').
document.documentElement.dataset.ready = 'true';
"""

STYLES = DESIGN_TOKENS + """*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.5;
}

main {
  max-width: 48rem;
  margin: 0 auto;
  padding: 1rem;
}
"""

PYTEST_INI = """[pytest]
DJANGO_SETTINGS_MODULE = {{package}}.settings
pythonpath = .
testpaths = tests
addopts = -p no:cacheprovider
"""

PACKAGE_JSON = """{
  "name": "{{project}}",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test:acceptance": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "%(playwright)s",
    "axe-core": "%(axe)s"
  }
}
""" % {"playwright": js.PLAYWRIGHT, "axe": js.AXE_CORE}

START = ".venv/bin/python manage.py migrate --noinput && exec .venv/bin/python manage.py runserver 127.0.0.1:$PORT --noreload"

SMOKE_UNIT = '''def test_the_home_page_renders(client):
    assert client.get("/").status_code == 200


def test_the_service_reports_its_health(client):
    assert client.get("/health").json() == {"status": "ok"}
'''

SMOKE_ACCEPTANCE = """import { test, expect } from '@playwright/test';

test('the page opens and the service answers', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(errors).toEqual([]);
  expect((await request.get('/health')).ok()).toBeTruthy();
});
"""

GUIDE = """The product is Django: settings in `{{package}}/settings.py`, addresses in
`{{package}}/urls.py`, views in `{{package}}/views.py`, page templates in
`{{package}}/templates/{{package}}/` and the page's own CSS and JavaScript in
`{{package}}/static/{{package}}/`. Models go in `{{package}}/models.py`; after changing one,
run `.venv/bin/python manage.py makemigrations` and keep the migration it writes.
JSON endpoints return `JsonResponse`. Unit tests go in `tests/`, named
`test_<area>.py`, as pytest functions taking pytest-django's `client` fixture (and
`db` for one that touches the database); run them with `.venv/bin/python -m pytest
tests`. Add a dependency to `requirements.txt` and run `.venv/bin/python -m pip install
-r requirements.txt`. Data lives in the database under `DATA_DIR`. Never start a server
yourself: the acceptance suite's configuration migrates the database and starts it."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `<feature>.spec.js`, using
`@playwright/test` (`import { test, expect } from '@playwright/test'`). The
configuration migrates a fresh database in an empty `DATA_DIR` and starts the
product; open a page with `await page.goto('/')` - never a `file://` address, a host
or a port. """ + js.FIND_CONTROLS + """ Act the way a user does: `fill`,
`click`, `press('Enter')`, `check`, `selectOption`. Test a JSON endpoint with the
`request` fixture, checking `response.status()` and `await response.json()`. To
prove something persists, change it, `await page.reload()`, and check it is still
there. Tests run one after another against the same product, so a test must create
what it reads and look for its own records rather than counting all of them.
""" + js.NAMING

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8000:8000 -e DJANGO_SECRET_KEY=... -v {{project}}-data:/app/data {{project}}`.
FROM python:%(python)s-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 DATA_DIR=/app/data DJANGO_DEBUG=0
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=collectstatic python manage.py collectstatic --noinput \\
    && useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn {{package}}.wsgi --bind \\"$HOST:$PORT\\""]
""" % {"python": _python.PYTHON_VERSION}

PACK = StackPack(
    name="fullstack-django",
    title="Browser app with its own HTTP service in Python on Django",
    kind="fullstack",
    language="python",
    frameworks=("django",),
    files={
        "requirements.txt": REQUIREMENTS,
        "requirements-dev.txt": REQUIREMENTS_DEV,
        "pytest.ini": PYTEST_INI,
        "manage.py": MANAGE,
        "{{package}}/__init__.py": '"""{{title}}."""\n',
        "{{package}}/settings.py": SETTINGS,
        "{{package}}/urls.py": URLS,
        "{{package}}/views.py": VIEWS,
        "{{package}}/wsgi.py": WSGI,
        "{{package}}/templates/{{package}}/home.html": HOME,
        "{{package}}/static/{{package}}/main.js": MAIN_JS,
        "{{package}}/static/{{package}}/styles.css": STYLES,
        "package.json": PACKAGE_JSON,
        "playwright.config.js": js.playwright_config(
            START, "/health", screenshot="on", checks_the_page=True, server_timeout_ms=120_000,
        ),
        "playwright.setup.mjs": js.page_check("/"),
        ".gitignore": js.GITIGNORE + _python.GITIGNORE + "staticfiles/\n",
    },
    install=(*js.INSTALL, *_python.INSTALL),
    unit_test=_python.UNIT_TEST,
    acceptance_test=js.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="tests",
    acceptance_dir="acceptance",
    acceptance_pattern="*.spec.js",
    unit_pattern="test_*.py",
    entrypoints=("{{package}}/urls.py", "{{package}}/templates/{{package}}/home.html"),
    unit_test_names=_python.UNIT_TEST_NAMES,
    test_helpers=_python.TEST_HELPERS,
    kept_files=("playwright.config.js", "playwright.setup.mjs", "pytest.ini"),
    kept_scripts={"test:acceptance": "playwright test"},
    smoke_files={
        "tests/test_scaffold_smoke.py": SMOKE_UNIT,
        "acceptance/scaffold-smoke.spec.js": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "Python",
        "framework": "Django",
        "frontend_framework": "None (Django templates with plain CSS and JavaScript)",
        "testing_framework": "pytest with pytest-django for unit tests, Playwright for acceptance tests",
    },
    # Python's checks only: the browser ones read pages as files, and a Django
    # template names its script and stylesheet with `{% static %}`, which they
    # would take for references to nothing.
    check_families=frozenset({"python"}),
    evidence_dir="test-results/evidence",
    test_bugs=js.TEST_BUGS + _python.TEST_BUGS,
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
    ci_setup=js.CI_SETUP + _python.CI_SETUP,
    ci_prepare=js.CI_BROWSERS,
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": _python.DOCKERIGNORE + "node_modules/\nstaticfiles/\n"},
)
