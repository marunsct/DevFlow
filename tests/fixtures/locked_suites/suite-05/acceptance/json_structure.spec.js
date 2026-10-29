import { test, expect } from '@playwright/test';

async function clearAllNotes(request) {
  const res = await request.get('/notes');
  if (res.status() !== 200) return;
  const notes = await res.json();
  for (const n of notes) {
    await request.delete(`/notes/${n.id}`);
  }
}

// AC-7: JSON structure validation.
test('[AC-7] POST and GET return note with correct fields', async ({ request }) => {
  await clearAllNotes(request);
  const post = await request.post('/notes', { data: { title: 'T', body: 'B' } });
  expect(post.status()).toBe(201);
  const created = await post.json();
  expect(created).toHaveProperty('id');
  expect(typeof created.id).toBe('number');
  expect(created.title).toBe('T');
  expect(created.body).toBe('B');
  // GET the same
  const get = await request.get(`/notes/${created.id}`);
  expect(get.status()).toBe(200);
  const got = await get.json();
  expect(got).toEqual(created);
});
