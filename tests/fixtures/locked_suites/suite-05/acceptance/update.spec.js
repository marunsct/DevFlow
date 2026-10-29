import { test, expect } from '@playwright/test';

// Helper to delete all notes by fetching list and deleting each.
async function clearAllNotes(request) {
  const res = await request.get('/notes');
  if (res.status() !== 200) return;
  const notes = await res.json();
  for (const n of notes) {
    await request.delete(`/notes/${n.id}`);
  }
}

// AC-4: Update a note's title and body.
test('[AC-4] PUT /notes/:id updates the note', async ({ request }) => {
  await clearAllNotes(request);
  const post = await request.post('/notes', { data: { title: 'Old', body: 'old' } });
  const created = await post.json();
  const upd = await request.put(`/notes/${created.id}`, { data: { title: 'New', body: 'new' } });
  expect(upd.status()).toBe(200);
  const json = await upd.json();
  expect(json.title).toBe('New');
  expect(json.body).toBe('new');
});

// AC-5: Delete a note.
test('[AC-5] DELETE /notes/:id deletes the note', async ({ request }) => {
  await clearAllNotes(request);
  const post = await request.post('/notes', { data: { title: 'Del', body: 'del' } });
  const created = await post.json();
  const del = await request.delete(`/notes/${created.id}`);
  expect(del.status()).toBe(204);
  // ensure it is gone
  const get = await request.get(`/notes/${created.id}`);
  expect(get.status()).toBe(404);
});
