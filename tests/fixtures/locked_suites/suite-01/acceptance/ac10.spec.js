import { test, expect } from '@playwright/test';

// AC-10: GET /notes/:id returns 200 or 404.

test('[AC-10] get single note status', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Exists' } });
  const created = await create.json();
  const id = created.id;

  const res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);

  const notFound = await request.get('/notes/9999');
  expect(notFound.status()).toBe(404);
});
