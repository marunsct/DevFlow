"""An HTTP service in PHP, on Slim."""

from __future__ import annotations

from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox

PHP_VERSION = "8.4"

#: PHPStan as a development dependency: the compile check (`app.analysis.compiler_check`) runs it at level 0 when the
#: project has it. Measured on one Slim run: three invented `Slim\\App` methods (`setStrictRouting`, `getErrorMiddleware`,
#: `setErrorHandler`) and a namespace declared after other code each stopped the product starting and were found only by
#: the next test round, five reverts in all; PHPStan names each at the write.
COMPOSER_JSON = """{
  "name": "app/{{project}}",
  "type": "project",
  "require": {
    "php": ">=8.2",
    "slim/slim": "^4.14",
    "slim/psr7": "^1.7"
  },
  "require-dev": {
    "phpstan/phpstan": "^2.1",
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

#: The pack's golden example (`StackPack.golden_example`), on Slim 4: the store made once in `create()` and handed to
#: each route's closure with `use`, the body read through `addBodyParsingMiddleware`, the error middleware added with
#: `addErrorMiddleware(bool, bool, bool)` (Slim 4 has no `getErrorMiddleware` or `setStrictRouting`), and a PHPUnit test
#: sending a JSON request through `handle`.
GOLDEN_SERVICE = r"""<?php

declare(strict_types=1);

namespace App;

use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\App as SlimApp;
use Slim\Factory\AppFactory;

/** Builds the service. public/index.php runs it; unit tests call it directly. */
final class Service
{
    public static function create(): SlimApp
    {
        // Shared state: one store, handed to each route that needs it.
        $store = new ItemStore(getenv('DATA_DIR') ?: 'data');
        $app = AppFactory::create();
        $app->addBodyParsingMiddleware();
        $app->addRoutingMiddleware();
        $app->addErrorMiddleware(false, true, true);

        $app->get('/health', function (Request $request, Response $response): Response {
            return self::json($response, 200, ['status' => 'ok']);
        });

        $app->post('/items', function (Request $request, Response $response) use ($store): Response {
            $body = $request->getParsedBody();
            $name = is_array($body) ? trim((string) ($body['name'] ?? '')) : '';
            if ($name === '') {
                return self::json($response, 400, ['error' => 'name is required']);
            }
            return self::json($response, 201, $store->add($name));
        });

        $app->get('/items/{id}', function (Request $request, Response $response, array $args) use ($store): Response {
            $item = $store->find((int) $args['id']);
            if ($item === null) {
                return self::json($response, 404, ['error' => 'item not found']);
            }
            return self::json($response, 200, $item);
        });

        return $app;
    }

    /** @param array<string, mixed> $value */
    private static function json(Response $response, int $status, array $value): Response
    {
        $response->getBody()->write((string) json_encode($value));
        return $response->withStatus($status)->withHeader('Content-Type', 'application/json');
    }
}
"""

GOLDEN_STORE = r"""<?php

declare(strict_types=1);

namespace App;

/** The items, kept in one JSON file under DATA_DIR; one lock covers each read-change-write. */
final class ItemStore
{
    private string $file;

    public function __construct(string $dataDir)
    {
        $this->file = rtrim($dataDir, '/') . '/items.json';
    }

    /** @return array{id: int, name: string} */
    public function add(string $name): array
    {
        return $this->locked(function (array $items) use ($name): array {
            $item = ['id' => $items === [] ? 1 : max(array_column($items, 'id')) + 1, 'name' => $name];
            $items[] = $item;
            return [$items, $item];
        });
    }

    /** @return array{id: int, name: string}|null */
    public function find(int $id): ?array
    {
        return $this->locked(function (array $items) use ($id): array {
            foreach ($items as $item) {
                if ($item['id'] === $id) {
                    return [null, $item];
                }
            }
            return [null, null];
        });
    }

    /** Runs $change on the items under the lock; it returns [the items to write, or null, and its result]. */
    private function locked(callable $change): mixed
    {
        $dir = dirname($this->file);
        if (!is_dir($dir)) {
            mkdir($dir, 0777, true);
        }
        $handle = fopen($this->file . '.lock', 'c');
        flock($handle, LOCK_EX);
        try {
            $items = is_file($this->file) ? json_decode((string) file_get_contents($this->file), true) : [];
            [$after, $result] = $change(is_array($items) ? $items : []);
            if ($after !== null) {
                file_put_contents($this->file, json_encode($after));
            }
            return $result;
        } finally {
            flock($handle, LOCK_UN);
            fclose($handle);
        }
    }
}
"""

GOLDEN_TEST = r"""<?php

declare(strict_types=1);

namespace Tests;

use App\Service;
use PHPUnit\Framework\TestCase;
use Psr\Http\Message\ResponseInterface;
use Slim\Psr7\Factory\ServerRequestFactory;

final class ItemsTest extends TestCase
{
    protected function setUp(): void
    {
        // Each test's service keeps its data in a folder of its own.
        putenv('DATA_DIR=' . sys_get_temp_dir() . '/items-' . bin2hex(random_bytes(6)));
    }

    private function send(string $method, string $path, ?string $json = null): ResponseInterface
    {
        $request = (new ServerRequestFactory())->createServerRequest($method, $path);
        if ($json !== null) {
            $request->getBody()->write($json);
            $request = $request->withHeader('Content-Type', 'application/json');
        }
        return Service::create()->handle($request);
    }

    public function testAnItemIsStoredAndReadBack(): void
    {
        $created = $this->send('POST', '/items', '{"name":"first"}');
        $this->assertSame(201, $created->getStatusCode());
        $item = json_decode((string) $created->getBody(), true);

        $found = $this->send('GET', '/items/' . $item['id']);
        $this->assertSame(200, $found->getStatusCode());
        $this->assertSame('first', json_decode((string) $found->getBody(), true)['name']);
    }

    public function testAMissingNameIsRefusedAndAnUnknownIdIsNotFound(): void
    {
        $this->assertSame(400, $this->send('POST', '/items', '{}')->getStatusCode());
        $this->assertSame(404, $this->send('GET', '/items/99')->getStatusCode());
    }
}
"""

PACK = service_pack(
    golden_example={"src/Service.php": GOLDEN_SERVICE, "src/ItemStore.php": GOLDEN_STORE,
                    "tests/ItemsTest.php": GOLDEN_TEST},
    sandbox_image=sandbox.PHP,
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
    entrypoint="src/Service.php",
    start='exec php -S "${HOST:-127.0.0.1}:$PORT" -t public public/index.php',
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
