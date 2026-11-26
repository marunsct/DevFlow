<?php

declare(strict_types=1);

namespace NotesApi\Domain;

/**
 * Pure value object representing a Note's unique identifier.
 */
final class NoteId
{
    public int $value;

    private function __construct(int $value)
    {
        if ($value <= 0) {
            throw new \InvalidArgumentException('Note ID must be a positive integer.');
        }
        $this->value = $value;
    }

    /**
     * Creates a NoteId instance from an integer value.
     *
     * @param int $value The integer value of the note ID.
     * @return self
     * @throws \InvalidArgumentException If value is not greater than 0.
     */
    public static function from(int $value): self
    {
        return new self($value);
    }

    /**
     * Returns the wrapped integer value.
     *
     * @return int
     */
    public function toInt(): int
    {
        return $this->value;
    }
}
