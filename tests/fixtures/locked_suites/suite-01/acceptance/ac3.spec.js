import { test, expect } from '@playwright/test';

// AC-3: Fetch one note by id – verifies 200 for existing and 404 for missing.

test('[AC-3] fetches a single note', async ({ request }) => {
  const create = await request.post('/notes', { data: { title: 'Only' } });
  const created = await create.json();
  const id = created.id;

  const res = await request.get(`/notes/${id}`);
  expect(res.status()).toBe(200);
  const fetched = await res.json();
  expect(fetched.title).toBe('Only');

  const notFound = await request.get('/notes/9999');
  expect(notFound.status()).toBe(404);
});
