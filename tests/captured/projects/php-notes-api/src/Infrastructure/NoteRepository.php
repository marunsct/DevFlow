<?php

declare(strict_types=1);

namespace NotesApi\Infrastructure;

use NotesApi\Domain\Note;
use NotesApi\Domain\NoteId;

/**
 * Interface for note persistence operations.
 */
interface NoteRepository
{
    /**
     * Inserts a new note into the database.
     *
     * @param Note $note The note to create.
     * @return NoteId The assigned ID for the new note.
     */
    public function create(Note $note): NoteId;

    /**
     * Selects all notes ordered by ID ascending.
     *
     * @return array<int, Note> An array of Note objects.
     */
    public function findAll(): array;

    /**
     * Selects a note by its ID.
     *
     * @param NoteId $id The unique identifier of the note.
     * @return Note|null The note if found, null otherwise.
     */
    public function findById(NoteId $id): ?Note;

    /**
     * Updates an existing note in a transaction.
     *
     * @param NoteId $id The ID of the note to update.
     * @param Note $note The updated note data.
     * @return bool True if the note was updated, false if not found.
     */
    public function update(NoteId $id, Note $note): bool;

    /**
     * Deletes a note by ID in a transaction.
     *
     * @param NoteId $id The ID of the note to delete.
     * @return bool True if the note was deleted, false if not found.
     */
    public function delete(NoteId $id): bool;
}
