<?php

declare(strict_types=1);

namespace NotesApi;

use Monolog\Handler\RotatingFileHandler;
use Monolog\Level;
use Monolog\Logger;
use NotesApi\Domain\NoteId;
use NotesApi\Handlers\CreateNoteHandler;
use NotesApi\Handlers\DeleteNoteHandler;
use NotesApi\Handlers\GetNoteHandler;
use NotesApi\Handlers\HealthCheckHandler;
use NotesApi\Handlers\ListNotesHandler;
use NotesApi\Handlers\UpdateNoteHandler;
use NotesApi\Infrastructure\NoteRepository;
use NotesApi\Infrastructure\PdoNoteRepository;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\App;
use Slim\Factory\AppFactory;

/**
 * Builds the service. public/index.php runs it; unit tests call it directly.
 */
final class Service
{
    /**
     * Creates and configures the Slim application.
     *
     * @return App The Slim application instance (PSR-15 callable).
     */
    public static function createApp(): App
    {
        // Ensure data directory exists
        $dataDir = getenv('DATA_DIR') ?: 'data';
        if (!is_dir($dataDir)) {
            mkdir($dataDir, 0777, true);
        }

        $app = AppFactory::create();

        // Register Middleware
        $app->add(new \NotesApi\Middleware\JsonBodyMiddleware());
        $app->add(new \NotesApi\Middleware\ErrorHandlingMiddleware());

        // Setup Logger
        $logger = new Logger('notes-api');
        $logger->pushHandler(new RotatingFileHandler($dataDir . '/notes-api.log', 30, Level::Debug));

        // Database Connection
        try {
            $pdo = new \PDO(
                'sqlite:' . $dataDir . '/notes.db',
                null,
                null,
                [
                    \PDO::ATTR_ERRMODE => \PDO::ERRMODE_EXCEPTION,
                    \PDO::ATTR_DEFAULT_FETCH_MODE => \PDO::FETCH_ASSOC,
                ]
            );
            $pdo->exec('PRAGMA journal_mode=WAL;');
            $pdo->exec('PRAGMA busy_timeout=5000;');

            // Ensure the notes table exists (id is auto-incrementing integer, title and body are text).
            $pdo->exec(
                'CREATE TABLE IF NOT EXISTS notes (' .
                '  id INTEGER PRIMARY KEY AUTOINCREMENT,' .
                '  title TEXT NOT NULL,' .
                '  body TEXT NOT NULL' .
                ')'
            );

            // Initialize Repository
            $repository = new PdoNoteRepository($pdo);

            // Register Handlers with DI-like wiring (passing repository to constructors).
            // Note: CreateNoteHandler and UpdateNoteHandler only accept NoteRepository as a constructor argument.
            // Passing $logger here would cause a TypeError because their __construct() signatures accept only one parameter.
            $createHandler = new CreateNoteHandler($repository);
            $listHandler = new ListNotesHandler($repository);
            $getHandler = new GetNoteHandler($repository);
            $updateHandler = new UpdateNoteHandler($repository);
            $deleteHandler = new DeleteNoteHandler($repository);
            $healthHandler = new HealthCheckHandler();

            // Register Routes
            $app->post('/notes', function (Request $request, Response $response) use ($createHandler): Response {
                return $createHandler($request, $response);
            });

            $app->get('/notes', function (Request $request, Response $response) use ($listHandler): Response {
                return $listHandler($request, $response);
            });

            $app->get('/notes/{id}', function (Request $request, Response $response, array $args) use ($getHandler): Response {
                return $getHandler($request, $response);
            });

            $app->put('/notes/{id}', function (Request $request, Response $response, array $args) use ($updateHandler): Response {
                return $updateHandler($request, $response);
            });

            $app->delete('/notes/{id}', function (Request $request, Response $response, array $args) use ($deleteHandler): Response {
                return $deleteHandler($request, $response);
            });

            $app->get('/health', function (Request $request, Response $response) use ($healthHandler): Response {
                return $healthHandler($request, $response);
            });

        } catch (\Throwable $e) {
            throw $e;
        }

        return $app;
    }
}
