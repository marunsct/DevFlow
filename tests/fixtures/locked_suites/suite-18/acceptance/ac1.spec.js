import { test, expect } from '@playwright/test';

// AC-1: Create a note with a title and a body – also covers AC-8
test('[AC-1][AC-8] Create a note with title and body', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: 'Test AC1', body: 'Body' } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toEqual(expect.objectContaining({ id: expect.any(Number), title: 'Test AC1', body: 'Body' }));
});
