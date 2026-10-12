"""An HTTP service in PHP, on Laravel."""

from __future__ import annotations

from app.stacks.packs import php_slim_api as php
from app.stacks.packs._service import service_pack

COMPOSER_JSON = """{
  "name": "app/{{project}}",
  "type": "project",
  "require": {
    "php": "^8.2",
    "laravel/framework": "^12.0"
  },
  "require-dev": {
    "phpunit/phpunit": "^11.5"
  },
  "autoload": {
    "psr-4": {
      "App\\\\": "app/",
      "Database\\\\Factories\\\\": "database/factories/",
      "Database\\\\Seeders\\\\": "database/seeders/"
    }
  },
  "autoload-dev": {
    "psr-4": { "Tests\\\\": "tests/" }
  },
  "config": {
    "sort-packages": true
  },
  "minimum-stability": "stable",
  "prefer-stable": true
}
"""

ARTISAN = """#!/usr/bin/env php
<?php

use Illuminate\\Foundation\\Application;
use Symfony\\Component\\Console\\Input\\ArgvInput;

define('LARAVEL_START', microtime(true));

require __DIR__.'/vendor/autoload.php';

/** @var Application $app */
$app = require_once __DIR__.'/bootstrap/app.php';

$status = $app->handleCommand(new ArgvInput);

exit($status);
"""

BOOTSTRAP = """<?php

use Illuminate\\Foundation\\Application;
use Illuminate\\Foundation\\Configuration\\Exceptions;
use Illuminate\\Foundation\\Configuration\\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        api: __DIR__.'/../routes/api.php',
        apiPrefix: '',
        commands: __DIR__.'/../routes/console.php',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        //
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        //
    })->create();
"""

ROUTES = """<?php

use Illuminate\\Support\\Facades\\Route;

Route::get('/health', fn () => ['status' => 'ok']);
"""

INDEX = """<?php

use Illuminate\\Http\\Request;

define('LARAVEL_START', microtime(true));

require __DIR__.'/../vendor/autoload.php';

(require_once __DIR__.'/../bootstrap/app.php')
    ->handleRequest(Request::capture());
"""

CONTROLLER = """<?php

namespace App\\Http\\Controllers;

abstract class Controller
{
    //
}
"""

#: What a developer's machine runs with; `php artisan key:generate` fills APP_KEY
#: when the project is set up, so no two projects share one.
ENV = """APP_NAME="{{title}}"
APP_ENV=local
APP_KEY=
APP_DEBUG=true
APP_URL=http://127.0.0.1
LOG_CHANNEL=stderr
DB_CONNECTION=sqlite
SESSION_DRIVER=array
CACHE_STORE=array
QUEUE_CONNECTION=sync
"""

TEST_CASE = """<?php

namespace Tests;

use Illuminate\\Foundation\\Testing\\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    //
}
"""

PHPUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Kept by the harness: the unit tests run through this file. -->
<phpunit bootstrap="vendor/autoload.php" colors="false" cacheDirectory=".phpunit.cache">
  <testsuites>
    <testsuite name="Feature">
      <directory>tests/Feature</directory>
    </testsuite>
    <testsuite name="Unit">
      <directory>tests/Unit</directory>
    </testsuite>
  </testsuites>
  <php>
    <env name="APP_ENV" value="testing"/>
    <env name="DB_CONNECTION" value="sqlite"/>
    <env name="DB_DATABASE" value=":memory:"/>
    <env name="CACHE_STORE" value="array"/>
    <env name="SESSION_DRIVER" value="array"/>
    <env name="QUEUE_CONNECTION" value="sync"/>
  </php>
</phpunit>
"""

SMOKE_UNIT = """<?php

namespace Tests\\Feature;

use Tests\\TestCase;

class ScaffoldSmokeTest extends TestCase
{
    public function test_the_service_reports_its_health(): void
    {
        $this->getJson('/health')->assertOk()->assertExactJson(['status' => 'ok']);
    }
}
"""

KEEP = "*\n!.gitignore\n"

GUIDE = """The service is PHP on Laravel: routes in `routes/api.php` (`Route::get`,
`Route::post` ...; served from the root, no `/api` prefix), controllers in
`app/Http/Controllers/`, models in `app/Models/`. Create a model and its migration
with `php artisan make:model <Name> -m`; `php artisan migrate` applies migrations.
Unit tests go in `tests/Feature/` (for routes: `$this->getJson('/items')
->assertOk()`) and `tests/Unit/`, named `<Name>Test.php`, extending `Tests\\TestCase`.
Run them with `vendor/bin/phpunit`. Add a package with `composer require
<vendor/package>`."""

START = (
    "mkdir -p $DATA_DIR && export DB_DATABASE=$DATA_DIR/database.sqlite && touch $DB_DATABASE "
    "&& php artisan migrate --force && exec php -S 127.0.0.1:$PORT -t public public/index.php"
)

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8080:8080 -e APP_KEY=base64:... -v {{project}}-data:/data {{project}}`.
FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json composer.lock* ./
RUN composer install --no-dev --no-interaction --no-progress --prefer-dist --no-scripts

FROM php:%(php)s-cli
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data APP_ENV=production APP_DEBUG=false LOG_CHANNEL=stderr DB_CONNECTION=sqlite
WORKDIR /app
COPY . .
COPY --from=vendor /app/vendor ./vendor
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app:app /data storage bootstrap/cache
USER app
EXPOSE 8080
CMD ["sh", "-c", "export DB_DATABASE=$DATA_DIR/database.sqlite && touch $DB_DATABASE && php artisan migrate --force && exec php -S \\"$HOST:$PORT\\" -t public public/index.php"]
""" % {"php": php.PHP_VERSION}

PACK = service_pack(
    name="php-laravel-api",
    title="HTTP service in PHP on Laravel",
    language="php",
    frameworks=("laravel",),
    files={
        "composer.json": COMPOSER_JSON,
        "artisan": ARTISAN,
        "bootstrap/app.php": BOOTSTRAP,
        "bootstrap/providers.php": "<?php\n\nreturn [];\n",
        "bootstrap/cache/.gitignore": KEEP,
        "routes/api.php": ROUTES,
        "routes/console.php": "<?php\n",
        "public/index.php": INDEX,
        "app/Http/Controllers/Controller.php": CONTROLLER,
        "app/Models/.gitkeep": "",
        "database/migrations/.gitkeep": "",
        "database/factories/.gitkeep": "",
        "database/seeders/.gitkeep": "",
        "storage/app/.gitignore": KEEP,
        "storage/framework/cache/data/.gitignore": KEEP,
        "storage/framework/sessions/.gitignore": KEEP,
        "storage/framework/views/.gitignore": KEEP,
        "storage/logs/.gitignore": KEEP,
        ".env": ENV,
        ".env.example": ENV,
        "phpunit.xml": PHPUNIT_XML,
        "tests/TestCase.php": TEST_CASE,
        "tests/Unit/.gitkeep": "",
    },
    install=(
        ("composer", "install", "--no-interaction", "--no-progress"),
        ("php", "artisan", "key:generate", "--force"),
    ),
    unit_test=php.PACK.unit_test,
    unit_report="test-results/unit.xml",
    unit_dir="tests",
    unit_pattern="*Test.php",
    start=START,
    server_timeout_ms=90_000,
    smoke_unit=("tests/Feature/ScaffoldSmokeTest.php", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "PHP",
        "framework": "Laravel",
        "frontend_framework": "",
        "testing_framework": "PHPUnit with Laravel's testing helpers for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=php.PACK.ci_setup[:1],
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\nvendor/\nacceptance/\ntests/\ndata/\n.env\n"},
    kept_files=("phpunit.xml",),
    gitignore="vendor/\n.phpunit.cache/\n.env\n",
)
