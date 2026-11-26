<?php

declare(strict_types=1);

namespace NotesApi;

use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\App;
use Slim\Factory\AppFactory;
use NotesApi\Middleware\ErrorHandler;
use NotesApi\Helpers\JsonResponse;
use NotesApi\Database;
use NotesApi\NoteService;
use NotesApi\Exceptions\ValidationException;

/**
 * Application bootstrap.
 *
 * Exports createApp(): App.
 * Creates the App, mounts routes, registers error handler, returns App.
 */
final class Service
{
    /**
     * Creates a new Slim App instance using AppFactory::create().
     * Sets the base path.
     * Mounts routes: POST /notes, GET /notes, GET /notes/{id}, PUT /notes/{id}, DELETE /notes/{id}, GET /health.
     * Registers the global ErrorHandler middleware.
     * Returns the configured App instance.
     *
     * @return App
     */
    public static function createApp(): App
    {
        $app = AppFactory::create();

        // Slim 4 requires explicit middleware for routing and body parsing.
        $app->addBodyParsingMiddleware();
        $app->addRoutingMiddleware();

        // Initialize database connection
        $dataDir = getenv('DATA_DIR') ?: 'data';
        $pdo = Database::connect($dataDir);

        // Register global error handler
        $app->add(new ErrorHandler());

        // GET /health
        $app->get('/health', function (Request $request, Response $response) {
            return JsonResponse::json($response, ['status' => 'ok'], 200);
        });

        // GET /notes
        $app->get('/notes', function (Request $request, Response $response) use ($pdo) {
            $notes = NoteService::fetchAll($pdo);
            return JsonResponse::json($response, $notes, 200);
        });

        // GET /notes/{id}
        $app->get('/notes/{id}', function (Request $request, Response $response, array $args) use ($pdo) {
            if (!ctype_digit((string) $args['id'])) {
                return JsonResponse::json($response, ['message' => 'Invalid note ID'], 400);
            }
            
            $id = (int) $args['id'];
            try {
                $note = NoteService::fetchNote($pdo, $id);
                return JsonResponse::json($response, $note, 200);
            } catch (\Exception $e) {
                if ($e->getMessage() === 'Note not found') {
                    return JsonResponse::json($response, ['message' => 'Note not found'], 404);
                }
                throw $e;
            }
        });

        // POST /notes
        $app->post('/notes', function (Request $request, Response $response) use ($pdo) {
            $contentType = $request->getHeaderLine('Content-Type');
            if (strpos($contentType, 'application/json') === false) {
                return JsonResponse::json($response, ['message' => 'Invalid JSON'], 400);
            }

            $body = $request->getParsedBody();
            
            if ($body === null || !is_array($body)) {
                return JsonResponse::json($response, ['message' => 'Invalid JSON'], 400);
            }

            // Check for missing keys
            if (!array_key_exists('title', $body)) {
                return JsonResponse::json($response, ['message' => 'Title is required'], 400);
            }
            if (!array_key_exists('body', $body)) {
                return JsonResponse::json($response, ['message' => 'Body is required'], 400);
            }

            $title = $body['title'];
            $bodyContent = $body['body'];

            // Validate types
            if (!is_string($title)) {
                return JsonResponse::json($response, ['message' => 'Title is required'], 400);
            }
            if (!is_string($bodyContent)) {
                return JsonResponse::json($response, ['message' => 'Body must be a string'], 400);
            }

            // Validate title content
            if (trim($title) === '') {
                return JsonResponse::json($response, ['message' => 'Title must not be empty'], 400);
            }

            try {
                $note = NoteService::createNote($pdo, $title, $bodyContent);
                return JsonResponse::json($response, $note, 201);
            } catch (ValidationException $e) {
                return JsonResponse::json($response, ['message' => $e->getMessage()], 400);
            }
        });

        // PUT /notes/{id}
        $app->put('/notes/{id}', function (Request $request, Response $response, array $args) use ($pdo) {
            if (!ctype_digit((string) $args['id'])) {
                return JsonResponse::json($response, ['message' => 'Invalid note ID'], 400);
            }

            $id = (int) $args['id'];
            
            $contentType = $request->getHeaderLine('Content-Type');
            if (strpos($contentType, 'application/json') === false) {
                return JsonResponse::json($response, ['message' => 'Invalid JSON'], 400);
            }

            $body = $request->getParsedBody();

            if ($body === null || !is_array($body)) {
                return JsonResponse::json($response, ['message' => 'Invalid JSON'], 400);
            }

            // Check for missing keys
            if (!array_key_exists('title', $body)) {
                return JsonResponse::json($response, ['message' => 'Title is required'], 400);
            }
            if (!array_key_exists('body', $body)) {
                return JsonResponse::json($response, ['message' => 'Body is required'], 400);
            }

            $title = $body['title'];
            $bodyContent = $body['body'];

            // Validate types
            if (!is_string($title)) {
                return JsonResponse::json($response, ['message' => 'Title is required'], 400);
            }
            if (!is_string($bodyContent)) {
                return JsonResponse::json($response, ['message' => 'Body must be a string'], 400);
            }

            if (trim($title) === '') {
                return JsonResponse::json($response, ['message' => 'Title must not be empty'], 400);
            }

            try {
                $note = NoteService::updateNote($pdo, $id, $title, $bodyContent);
                return JsonResponse::json($response, $note, 200);
            } catch (ValidationException $e) {
                return JsonResponse::json($response, ['message' => $e->getMessage()], 400);
            } catch (\Exception $e) {
                if ($e->getMessage() === 'Note not found') {
                    return JsonResponse::json($response, ['message' => 'Note not found'], 404);
                }
                throw $e;
            }
        });

        // DELETE /notes/{id}
        $app->delete('/notes/{id}', function (Request $request, Response $response, array $args) use ($pdo) {
            if (!ctype_digit((string) $args['id'])) {
                return JsonResponse::json($response, ['message' => 'Invalid note ID'], 400);
            }

            $id = (int) $args['id'];
            $deleted = NoteService::deleteNote($pdo, $id);
            if ($deleted) {
                return $response->withStatus(204);
            }
            return JsonResponse::json($response, ['message' => 'Note not found'], 404);
        });

        return $app;
    }
}
