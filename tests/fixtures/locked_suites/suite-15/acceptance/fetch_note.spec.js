import { test, expect } from '@playwright/test';

// AC-3: Fetch a note by id and 404 for missing
// Create a known note then fetch it; also test non‑existent id.
test('[AC-3][AC-10] GET /notes/:id returns the note or 404', async ({ request }) => {
  // create note
  const res = await request.post('/notes', { data: { title: 'Fetch', body: 'Data' } });
  expect(res.status()).toBe(201);
  const created = await res.json();
  const id = created.id;
  // fetch existing
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched).toEqual(created);
  // fetch non-existent
  const missingRes = await request.get('/notes/99999');
  expect(missingRes.status()).toBe(404);
  const missJson = await missingRes.json();
  expect(missJson).toEqual({ error: 'Not found' });
});
