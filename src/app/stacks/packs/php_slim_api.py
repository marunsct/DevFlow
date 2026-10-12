"""An HTTP service in PHP, on Slim."""

from __future__ import annotations

from app.stacks.packs._service import service_pack

PHP_VERSION = "8.4"

COMPOSER_JSON = """{
  "name": "app/{{project}}",
  "type": "project",
  "require": {
    "php": ">=8.2",
    "slim/slim": "^4.14",
    "slim/psr7": "^1.7"
  },
  "require-dev": {
    "phpunit/phpunit": "^11.5"
  },
  "autoload": {
    "psr-4": { "App\\\\": "src/" }
  },
  "autoload-dev": {
    "psr-4": { "Tests\\\\": "tests/" }
  },
  "config": {
    "sort-packages": true
  }
}
"""

SERVICE = """<?php

declare(strict_types=1);

namespace App;

use Psr\\Http\\Message\\ResponseInterface as Response;
use Psr\\Http\\Message\\ServerRequestInterface as Request;
use Slim\\App as SlimApp;
use Slim\\Factory\\AppFactory;

/** Builds the service. public/index.php runs it; unit tests call it directly. */
final class Service
{
    public static function create(): SlimApp
    {
        $app = AppFactory::create();
        $app->addBodyParsingMiddleware();
        $app->get('/health', function (Request $request, Response $response): Response {
            $response->getBody()->write((string) json_encode(['status' => 'ok']));
            return $response->withHeader('Content-Type', 'application/json');
        });
        return $app;
    }
}
"""

INDEX = """<?php

declare(strict_types=1);

require __DIR__ . '/../vendor/autoload.php';

App\\Service::create()->run();
"""

PHPUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Kept by the harness: the unit tests run through this file. -->
<phpunit bootstrap="vendor/autoload.php" colors="false" cacheDirectory=".phpunit.cache">
  <testsuites>
    <testsuite name="unit">
      <directory>tests</directory>
    </testsuite>
  </testsuites>
</phpunit>
"""

SMOKE_UNIT = """<?php

declare(strict_types=1);

namespace Tests;

use App\\Service;
use PHPUnit\\Framework\\TestCase;
use Slim\\Psr7\\Factory\\ServerRequestFactory;

final class ScaffoldSmokeTest extends TestCase
{
    public function testTheServiceReportsItsHealth(): void
    {
        $request = (new ServerRequestFactory())->createServerRequest('GET', '/health');
        $response = Service::create()->handle($request);
        $this->assertSame(200, $response->getStatusCode());
        $this->assertSame(['status' => 'ok'], json_decode((string) $response->getBody(), true));
    }
}
"""

GUIDE = """The service is PHP on Slim 4: `Service::create()` in `src/Service.php` builds the
application (add routes with `$app->get`, `$app->post` ...; put other classes in
`src/`, namespace `App`), and `public/index.php` runs it. Unit tests go in `tests/`,
named `<Name>Test.php`, namespace `Tests`, extending PHPUnit's `TestCase` and calling
`Service::create()->handle($request)` directly. Run them with `vendor/bin/phpunit`.
Add a package with `composer require <vendor/package>`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8080:8080 -v {{project}}-data:/data {{project}}`.
FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json composer.lock* ./
RUN composer install --no-dev --no-interaction --no-progress --prefer-dist

FROM php:%(php)s-cli
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data
WORKDIR /app
COPY . .
COPY --from=vendor /app/vendor ./vendor
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec php -S \\"$HOST:$PORT\\" -t public public/index.php"]
""" % {"php": PHP_VERSION}

PACK = service_pack(
    name="php-slim-api",
    title="HTTP service in PHP on Slim",
    language="php",
    frameworks=("slim", "slim framework", "slim 4"),
    files={
        "composer.json": COMPOSER_JSON,
        "src/Service.php": SERVICE,
        "public/index.php": INDEX,
        "phpunit.xml": PHPUNIT_XML,
    },
    install=(("composer", "install", "--no-interaction", "--no-progress"),),
    unit_test=("vendor/bin/phpunit", "--log-junit", "test-results/unit.xml"),
    unit_report="test-results/unit.xml",
    unit_dir="tests",
    unit_pattern="*Test.php",
    start="exec php -S 127.0.0.1:$PORT -t public public/index.php",
    server_timeout_ms=60_000,
    smoke_unit=("tests/ScaffoldSmokeTest.php", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "PHP",
        "framework": "Slim",
        "frontend_framework": "",
        "testing_framework": "PHPUnit for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(
        "      - uses: shivammathur/setup-php@v2\n"
        "        with:\n"
        f'          php-version: "{PHP_VERSION}"',
    ),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\nvendor/\nacceptance/\ntests/\ndata/\n"},
    kept_files=("phpunit.xml",),
    gitignore="vendor/\n.phpunit.cache/\n",
)
