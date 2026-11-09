import { test, expect } from '@playwright/test';

// Test that a note can be updated via PUT and the service returns 200 with the updated note.
// This verifies AC-11: PUT /notes/{id} replaces both title and body, answers 200 with the note or 404.

test('[AC-11] PUT /notes/:id updates title and body', async ({ request }) => {
  // Create a note first
  const createRes = await request.post('/notes', { data: { title: 'Original', body: 'Orig' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;

  // Update the note
  const updateRes = await request.put(`/notes/${id}`, { data: { title: 'Updated', body: 'New' } });
  expect(updateRes.status()).toBe(200);
  const updated = await updateRes.json();
  expect(updated).toEqual({ id, title: 'Updated', body: 'New' });

  // Verify GET returns updated values
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const got = await getRes.json();
  expect(got).toEqual(updated);
});
