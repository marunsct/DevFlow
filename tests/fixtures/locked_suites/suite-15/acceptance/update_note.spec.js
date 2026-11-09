import { test, expect } from '@playwright/test';

// AC-4: Update a note's title and body
// Create a note then PUT new values; verify status 200 and updated content.
test('[AC-4][AC-11] PUT /notes/:id updates the note', async ({ request }) => {
  const createRes = await request.post('/notes', { data: { title: 'Old', body: 'Data' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;
  const updateRes = await request.put(`/notes/${id}`, { data: { title: 'New', body: 'Updated' } });
  expect(updateRes.status()).toBe(200);
  const updated = await updateRes.json();
  expect(updated.id).toBe(id);
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('Updated');
});
