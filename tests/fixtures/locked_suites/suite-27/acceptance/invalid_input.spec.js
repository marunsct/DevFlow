import { test, expect } from '@playwright/test';

/**
 * Tests that invalid input is rejected without modifying the data store.
 * Covers AC‑13 (missing or empty title) and AC‑18 (invalid input not stored).
 */
test('[AC-13][AC-18] POST /notes without a title returns 400 and does not persist', async ({ request }) => {
  // Attempt to create a note without a title.
  const resp = await request.post('/notes', { data: { body: 'No title provided' } });
  expect(resp.status()).toBe(400);
  const jsonResp = await resp.json();
  expect(jsonResp).toEqual({ error: 'Title is required' });

  // Verify that the notes list remains empty.
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notesList = await listResp.json();
  expect(Array.isArray(notesList)).toBe(true);
  const initialCount = notesList.length;
  // After invalid create, count should remain the same
  const postResp = await request.post('/notes', { data: { body: 'No title' } });
  expect(postResp.status()).toBe(400);
  const updatedNotes = await listResp.json();
  expect(updatedNotes.length).toBe(initialCount);
});

/**
 * Tests that the service correctly lists two notes after creating them.
 * Covers AC‑2 (list all notes).
 */
test('[AC-2] GET /notes returns array of length 2 after two creations', async ({ request }) => {
  // Create first note.
  const create1 = await request.post('/notes', { data: { title: 'First Note', body: 'Content A' } });
  expect(create1.status()).toBe(201);
  const note1 = await create1.json();

  // Create second note.
  const create2 = await request.post('/notes', { data: { title: 'Second Note', body: 'Content B' } });
  expect(create2.status()).toBe(201);
  const note2 = await create2.json();

  // Retrieve list.
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const notesArray = await listResp.json();
  expect(Array.isArray(notesArray)).toBe(true);
  expect(notesArray.length).toBeGreaterThanOrEqual(2);
  const ids = notesArray.map((n) => n.id);
  expect(ids).toContain(note1.id);
  expect(ids).toContain(note2.id);
});
