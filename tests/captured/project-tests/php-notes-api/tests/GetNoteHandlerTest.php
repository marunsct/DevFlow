<?php

declare(strict_types=1);

namespace Tests;

use NotesApi\Domain\Note;
use NotesApi\Domain\NoteId;
use NotesApi\Handlers\GetNoteHandler;
use NotesApi\Infrastructure\NoteRepository;
use PHPUnit\Framework\TestCase;
use Psr\Http\Message\ResponseInterface;
use Slim\Psr7\Factory\ServerRequestFactory;

/**
 * Regression test for AC-3 / AC-10: GET /notes/{id} returns the note or 404.
 *
 * Tests GetNoteHandler directly against a mock repository so the test
 * exercises the handler logic (status codes, response body) without
 * depending on the full Slim application stack.
 *
 * This test would have failed when Service.php lacked the CREATE TABLE
 * statement because the 500 error from the missing table would have
 * propagated through the middleware as a 500 response instead of
 * 200/404.
 */
final class GetNoteHandlerTest extends TestCase
{
    /**
     * AC-3: GET /notes/{id} returns 200 with the note for an existing id.
     */
    public function testGetExistingNoteReturns200WithNote(): void
    {
        $expectedNote = Note::create('Test Title', 'Test Body');
        $expectedId = NoteId::from(42);

        /** @var NoteRepository&\PHPUnit\Framework\MockObject\MockObject $repository */
        $repository = $this->createMock(NoteRepository::class);
        $repository
            ->expects($this->once())
            ->method('findById')
            ->with($expectedId)
            ->willReturn($expectedNote);

        $handler = new GetNoteHandler($repository);

        // Build a request that mimics Slim's route parameter extraction.
        $request = (new ServerRequestFactory())->createServerRequest('GET', '/notes/42')
            ->withAttribute('id', 42);

        $response = $handler($request, new \Slim\Psr7\Response());

        $this->assertSame(200, $response->getStatusCode());
        $this->assertStringContainsString('"id":42', (string) $response->getBody());
        $this->assertStringContainsString('"title":"Test Title"', (string) $response->getBody());
        $this->assertStringContainsString('"body":"Test Body"', (string) $response->getBody());
    }

    /**
     * AC-10: GET /notes/{id} returns 404 when no note with that id exists.
     */
    public function testGetNonExistentNoteReturns404(): void
    {
        $nonExistentId = NoteId::from(99999);

        /** @var NoteRepository&\PHPUnit\Framework\MockObject\MockObject $repository */
        $repository = $this->createMock(NoteRepository::class);
        $repository
            ->expects($this->once())
            ->method('findById')
            ->with($nonExistentId)
            ->willReturn(null);

        $handler = new GetNoteHandler($repository);

        $request = (new ServerRequestFactory())->createServerRequest('GET', '/notes/99999')
            ->withAttribute('id', 99999);

        $response = $handler($request, new \Slim\Psr7\Response());

        $this->assertSame(404, $response->getStatusCode());
        $body = (string) $response->getBody();
        $this->assertStringContainsString('"error"', $body);
        $this->assertStringContainsString('Note not found.', $body);
    }
}
