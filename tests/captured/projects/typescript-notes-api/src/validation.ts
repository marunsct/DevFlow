/**
 * Input validation for note creation and update requests.
 *
 * This module provides pure validation functions that check the shape and
 * content of incoming request bodies before they reach the store layer.
 * Validation errors return descriptive messages that are sent directly to
 * clients as 400 responses (per ADR-07).
 *
 * No file I/O, no side effects — safe to import in tests without touching
 * the filesystem or the network.
 */

/**
 * Result shape returned by validateNoteBody.
 *
 * When valid: { valid: true, data: { title, body } }
 * When invalid: { valid: false, error: string }
 */
export interface ValidationResult {
  valid: boolean;
  // Present when valid is true — the validated and normalised note data.
  data?: { title: string; body: string };
  // Present when valid is false — a human-readable description of the failure.
  error?: string;
}

/**
 * Validates the request body for note create/update operations.
 *
 * Checks that:
 * - body is a non-null object (not an array, not null, not primitive)
 * - title is present, is a string, and is non-empty after trimming whitespace
 * - body field is present and is a string (empty strings are allowed per ADR-03)
 *
 * @param body — The parsed request body from the HTTP handler. Must be an object.
 * @returns { valid: true, data } if all checks pass, or { valid: false, error } on first failure.
 */
export function validateNoteBody(body: unknown): ValidationResult {
  // Check that body is a non-null object (arrays and null are excluded)
  if (body === null || typeof body !== 'object') {
    return { valid: false, error: 'Invalid request body' };
  }

  const parsed = body as Record<string, unknown>;
  const title = parsed.title;
  const noteBody = parsed.body;

  // Validate title: must be present, a string, and non-empty after trim
  if (title === undefined || title === null) {
    return { valid: false, error: 'Title is required and must not be empty' };
  }

  if (typeof title !== 'string') {
    return { valid: false, error: 'Title is required and must not be empty' };
  }

  if (title.trim() === '') {
    return { valid: false, error: 'Title is required and must not be empty' };
  }

  // Validate body field: must be present and a string
  if (noteBody === undefined || noteBody === null) {
    return { valid: false, error: 'Body is required' };
  }

  if (typeof noteBody !== 'string') {
    return { valid: false, error: 'Body is required' };
  }

  // All checks passed — return the validated data
  return { valid: true, data: { title: title.trim(), body: noteBody } };
}
