import { test, expect } from '@playwright/test';

// Test AC-10: GET /notes/:id returns note or 404
// Creates a note and verifies retrieval; also checks 404 for missing id.
test('[AC-10] GET /notes/:id returns note or 404', async ({ request }) => {
  const create = async (title, body) => {
    const res = await request.post('/notes', { data: { title, body } });
    expect(res.status()).toBe(201);
    return (await res.json());
  };
  const note = await create('Single', 'Only');
  const getRes = await request.get(`/notes/${note.id}`);
  expect(getRes.status()).toBe(200);
  expect(await getRes.json()).toEqual(note);

  const notFound = await request.get('/notes/9999');
  expect(notFound.status()).toBe(404);
  expect(await notFound.json()).toEqual({ error: 'Not found' });
});
