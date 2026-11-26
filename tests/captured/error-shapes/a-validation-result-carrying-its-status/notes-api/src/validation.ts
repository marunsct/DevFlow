export type NoteBodyResult =
  | { ok: true; title: string; body: string }
  | { ok: false; status: 400 | 422; error: string };

export function parseNoteBody(input: unknown): NoteBodyResult {
  if (input === null || typeof input !== 'object' || Array.isArray(input)) {
    return { ok: false, status: 400, error: 'request body must be a JSON object' };
  }
  const obj = input as Record<string, unknown>;
  const title = obj.title;
  if (typeof title !== 'string' || title.trim() === '') {
    return { ok: false, status: 422, error: 'title is required and must be a non-empty string' };
  }
  const body = obj.body;
  if (body === undefined) {
    return { ok: true, title, body: '' };
  }
  if (typeof body !== 'string') {
    return { ok: false, status: 422, error: 'body must be a string' };
  }
  return { ok: true, title, body };
}

export function parseId(segment: string | undefined): number | null {
  if (segment === undefined) return null;
  if (!/^[0-9]+$/.test(segment)) return null;
  const value = Number(segment);
  if (!Number.isSafeInteger(value) || value <= 0) return null;
  return value;
}
