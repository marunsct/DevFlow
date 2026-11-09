import { test, expect } from '@playwright/test';

/**
 * Tests that non‑numeric id values are rejected on GET and DELETE.
 */

// GET /notes/:id with a non‑numeric id should return 400 and the expected error message.
test('[AC-13] GET /notes/:id with invalid id returns 400', async ({ request }) => {
  const res = await request.get('/notes/abc');
  expect(res.status()).toBe(400);
  const body = await res.json();
  expect(body).toEqual({ message: 'invalid id format' });
});

// DELETE /notes/:id with a non‑numeric id should return 400 and the expected error message.
test('[AC-13] DELETE /notes/:id with invalid id returns 400', async ({ request }) => {
  const res = await request.delete('/notes/xyz');
  expect(res.status()).toBe(400);
  const body = await res.json();
  expect(body).toEqual({ message: 'invalid id format' });
});
