<?php

declare(strict_types=1);

namespace NotesApi\Handlers;

use NotesApi\Domain\NoteId;
use NotesApi\Infrastructure\NoteRepository;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;
use Slim\Psr7\Response as SlimResponse;

class GetNoteHandler
{
    private NoteRepository $repository;

    public function __construct(NoteRepository $repository)
    {
        $this->repository = $repository;
    }

    /**
     * @param Request $request
     * @param Response $response
     * @return Response
     */
    public function __invoke(Request $request, Response $response): Response
    {
        try {
            $id = (int) $request->getAttribute('id');

            $noteId = NoteId::from($id);

            $note = $this->repository->findById($noteId);

            if ($note === null) {
                $response->getBody()->write(json_encode(['error' => 'Note not found.']));
                return $response
                    ->withStatus(404)
                    ->withHeader('Content-Type', 'application/json');
            }

            $response->getBody()->write(json_encode($note->toArray()));
            return $response
                ->withStatus(200)
                ->withHeader('Content-Type', 'application/json');
        } catch (\Throwable $e) {
            throw $e;
        }
    }
}
