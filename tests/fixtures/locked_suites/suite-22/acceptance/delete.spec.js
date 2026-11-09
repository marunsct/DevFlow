import { test, expect } from '@playwright/test';

// Test AC-12: DELETE /notes/{id} returns 204 and removes the note.
// The test creates a note first, deletes it, then verifies deletion.
test('[AC-12] deletes a note with status 204', async ({ request }) => {
  // Create a note to delete
  const createRes = await request.post('/notes', { data: { title: 'To be deleted', body: 'Will vanish' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  const id = created.id;

  // Delete the note
  const delRes = await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  // No body should be returned for 204; fetch to confirm
  const getAfterDel = await request.get(`/notes/${id}`);
  expect(getAfterDel.status()).toBe(404);
});
