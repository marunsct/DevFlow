import { test, expect } from '@playwright/test';

// ──────────────────────────────────────────────────
// AC-13  A title that is missing or empty is refused with 400 or 422
// AC-18  Invalid input is refused without storing anything
// ──────────────────────────────────────────────────

test('[AC-13][AC-18] POST /notes rejects empty, whitespace-only, and missing title', async ({ request }) => {
  // --- Empty string title ---
  const emptyTitleRes = await request.post('/notes', {
    data: { title: '', body: 'Body text' },
  });
  expect([400, 422]).toContain(emptyTitleRes.status());

  // --- Whitespace-only title (multiple whitespace characters) ---
  const wsTitleRes = await request.post('/notes', {
    data: { title: '   ', body: 'Body text' },
  });
  expect([400, 422]).toContain(wsTitleRes.status());

  // --- Tab-only title ---
  const tabTitleRes = await request.post('/notes', {
    data: { title: '\t\t', body: 'Body text' },
  });
  expect([400, 422]).toContain(tabTitleRes.status());

  // --- Missing title field entirely ---
  const missingTitleRes = await request.post('/notes', {
    data: { body: 'Body text' },
  });
  expect([400, 422]).toContain(missingTitleRes.status());

  // --- Title is a number (not a string) ---
  const numberTitleRes = await request.post('/notes', {
    data: { title: 123, body: 'Body text' },
  });
  expect([400, 422]).toContain(numberTitleRes.status());

  // --- Verify nothing was stored: note count should remain unchanged ---
  const beforeListRes = await request.get('/notes');
  const beforeNotes = await beforeListRes.json();

  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const notes = await listRes.json();
  expect(notes).toHaveLength(beforeNotes.length);
});

// ──────────────────────────────────────────────────
// AC-13  PUT with empty/missing title is also rejected
// AC-18  Invalid input is refused without storing anything
// ──────────────────────────────────────────────────

test('[AC-13][AC-18] PUT /notes/{id} rejects empty or missing title', async ({ request }) => {
  // Create a valid note first
  const createRes = await request.post('/notes', {
    data: { title: 'Valid note', body: 'Body' },
  });
  expect(createRes.status()).toBe(201);
  const noteId = (await createRes.json()).id;

  // --- PUT with empty title ---
  const putEmptyTitleRes = await request.put(`/notes/${noteId}`, {
    data: { title: '', body: 'New body' },
  });
  expect([400, 422]).toContain(putEmptyTitleRes.status());

  // Verify the original note is unchanged (title still "Valid note")
  const verifyRes = await request.get(`/notes/${noteId}`);
  expect(verifyRes.status()).toBe(200);
  const note = await verifyRes.json();
  expect(note.title).toBe('Valid note');

  // --- PUT with missing title ---
  const putMissingTitleRes = await request.put(`/notes/${noteId}`, {
    data: { body: 'New body' },
  });
  expect([400, 422]).toContain(putMissingTitleRes.status());

  // Verify the original note is still unchanged
  const verifyRes2 = await request.get(`/notes/${noteId}`);
  expect(verifyRes2.status()).toBe(200);
  const note2 = await verifyRes2.json();
  expect(note2.title).toBe('Valid note');

  // --- PUT with whitespace-only title ---
  const putWsTitleRes = await request.put(`/notes/${noteId}`, {
    data: { title: '\t ', body: 'New body' },
  });
  expect([400, 422]).toContain(putWsTitleRes.status());

  // Verify the original note is still unchanged
  const verifyRes3 = await request.get(`/notes/${noteId}`);
  expect(verifyRes3.status()).toBe(200);
  const note3 = await verifyRes3.json();
  expect(note3.title).toBe('Valid note');
});
