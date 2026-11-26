<?php

declare(strict_types=1);

namespace NotesApi\Infrastructure;

use NotesApi\Domain\Note;
use NotesApi\Domain\NoteId;
use PDO;
use PDOException;

/**
 * SQLite-backed implementation of NoteRepository.
 */
final class PdoNoteRepository implements NoteRepository
{
    private PDO $pdo;

    /**
     * @param PDO $pdo SQLite connection with WAL mode already configured.
     */
    public function __construct(PDO $pdo)
    {
        $this->pdo = $pdo;
    }

    /**
     * Inserts a new note into the database.
     *
     * @param Note $note The note to create.
     * @return NoteId The assigned ID for the new note.
     * @throws PDOException If a database error occurs.
     */
    public function create(Note $note): NoteId
    {
        try {
            $this->pdo->beginTransaction();

            $stmt = $this->pdo->prepare('INSERT INTO notes (title, body) VALUES (:title, :body)');
            $stmt->execute([
                ':title' => $note->getTitle(),
                ':body' => $note->getBody(),
            ]);

            $id = (int) $this->pdo->lastInsertId();

            $this->pdo->commit();

            return NoteId::from($id);
        } catch (\Throwable $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            throw $e;
        }
    }

    /**
     * Selects all notes ordered by ID ascending.
     *
     * @return array<int, Note> An array of Note objects.
     */
    public function findAll(): array
    {
        $stmt = $this->pdo->query('SELECT id, title, body FROM notes ORDER BY id ASC');
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

        $notes = [];
        foreach ($rows as $row) {
            // Create a Note instance with the ID from the database.
            // We use a temporary construction since create() validates title,
            // but here we are just hydrating existing data which is assumed valid.
            // However, to adhere strictly to the value object pattern where create() throws on bad titles,
            // and assuming DB integrity holds for existing records:
            $note = Note::create($row['title'], $row['body']);
            $notes[] = $note->withId((int) $row['id']);
        }

        return $notes;
    }

    /**
     * Selects a note by ID.
     *
     * @param NoteId $id The unique identifier of the note.
     * @return Note|null The note if found, null otherwise.
     */
    public function findById(NoteId $id): ?Note
    {
        $stmt = $this->pdo->prepare('SELECT id, title, body FROM notes WHERE id = :id');
        $stmt->execute([':id' => $id->toInt()]);

        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($row === false) {
            return null;
        }

        $note = Note::create($row['title'], $row['body']);
        return $note->withId((int) $row['id']);
    }

    /**
     * Updates an existing note in a transaction.
     *
     * @param NoteId $id The ID of the note to update.
     * @param Note $note The updated note data.
     * @return bool True if the note was updated, false if not found.
     */
    public function update(NoteId $id, Note $note): bool
    {
        try {
            $this->pdo->beginTransaction();

            $stmt = $this->pdo->prepare('UPDATE notes SET title = :title, body = :body WHERE id = :id');
            $stmt->execute([
                ':title' => $note->getTitle(),
                ':body' => $note->getBody(),
                ':id' => $id->toInt(),
            ]);

            $affected = $stmt->rowCount();

            $this->pdo->commit();

            return $affected > 0;
        } catch (\Throwable $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            throw $e;
        }
    }

    /**
     * Deletes a note by ID in a transaction.
     *
     * @param NoteId $id The ID of the note to delete.
     * @return bool True if the note was deleted, false if not found.
     */
    public function delete(NoteId $id): bool
    {
        try {
            $this->pdo->beginTransaction();

            $stmt = $this->pdo->prepare('DELETE FROM notes WHERE id = :id');
            $stmt->execute([':id' => $id->toInt()]);

            $affected = $stmt->rowCount();

            $this->pdo->commit();

            return $affected > 0;
        } catch (\Throwable $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            throw $e;
        }
    }
}
