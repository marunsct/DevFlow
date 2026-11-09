import { test, expect } from '@playwright/test';

// Verify that PUT /notes/:id with missing or empty title returns 400 and does not modify the note.

test('[AC-4] PUT /notes/:id rejects missing or empty title', async ({ request }) => {
  // First create a valid note
  const createRes = await request.post('/notes', { data: { title: 'Original', body: 'Body' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;

  // Attempt to update with empty title
  const updEmpty = await request.put(`/notes/${id}`, { data: { title: '', body: 'New' } });
  expect(updEmpty.status()).toBe(400);
  const err1 = await updEmpty.json();
  expect(err1).toEqual({ error: 'title required' });

  // Attempt to update with missing title field
  const updMissing = await request.put(`/notes/${id}`, { data: { body: 'New' } });
  expect(updMissing.status()).toBe(400);
  const err2 = await updMissing.json();
  expect(err2).toEqual({ error: 'title required' });

  // Verify the note remains unchanged
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const after = await getRes.json();
  expect(after.title).toBe('Original');
});
