<?php

declare(strict_types=1);

namespace NotesApi\Domain;

/**
 * Pure value object representing a Note entity.
 */
final class Note
{
    private int $id;
    private string $title;
    private string $body;

    /**
     * @param int $id Auto-incrementing ID assigned by the database (0 if not yet persisted).
     * @param string $title The note's title.
     * @param string $body The note's body content.
     */
    private function __construct(int $id, string $title, string $body)
    {
        $this->id = $id;
        $this->title = $title;
        $this->body = $body;
    }

    /**
     * Creates a new Note instance after validating the title.
     *
     * @param string $title The note's title (must not be null, empty, or whitespace-only).
     * @param string $body The note's body content (may be empty).
     * @return Note
     * @throws \InvalidArgumentException If title validation fails.
     */
    public static function create(string $title, string $body): self
    {
        if ($title === '' || preg_match('/^\s*$/', $title)) {
            throw new \InvalidArgumentException('Title must not be empty.');
        }

        // ID is assigned by the repository/database upon persistence.
        return new self(0, $title, $body);
    }

    /**
     * Creates an updated Note instance from an existing one.
     *
     * @param Note $note The existing note to update.
     * @param string $newTitle The new title (must not be null, empty, or whitespace-only).
     * @param string $newBody The new body content.
     * @return Note
     * @throws \InvalidArgumentException If newTitle validation fails.
     */
    public static function update(self $note, string $newTitle, string $newBody): self
    {
        if ($newTitle === '' || preg_match('/^\s*$/', $newTitle)) {
            throw new \InvalidArgumentException('Title must not be empty.');
        }

        return new self($note->id, $newTitle, $newBody);
    }

    /**
     * Returns the note's ID.
     *
     * @return int
     */
    public function getId(): int
    {
        return $this->id;
    }

    /**
     * Sets the note's ID (typically used after persistence).
     *
     * @param int $id
     * @return self
     */
    public function withId(int $id): self
    {
        $note = new self($id, $this->title, $this->body);
        return $note;
    }

    /**
     * Returns the note's title.
     *
     * @return string
     */
    public function getTitle(): string
    {
        return $this->title;
    }

    /**
     * Returns the note's body.
     *
     * @return string
     */
    public function getBody(): string
    {
        return $this->body;
    }

    /**
     * Returns an associative array representation of the note.
     *
     * @return array{id: int, title: string, body: string}
     */
    public function toArray(): array
    {
        return [
            'id' => $this->id,
            'title' => $this->title,
            'body' => $this->body,
        ];
    }
}
