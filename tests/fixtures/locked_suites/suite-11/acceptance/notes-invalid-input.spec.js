import { test, expect } from '@playwright/test';

// AC-18: Invalid JSON payload is refused and no note is stored
const malformed = 'this is not json';

test('[AC-18] POST /notes with invalid JSON returns 400 and does not create a note', async ({ request }) => {
  // capture list before
  const beforeRes = await request.get('/notes');
  expect(beforeRes.status()).toBe(200);
  const beforeList = await beforeRes.json();
  const initialCount = Array.isArray(beforeList) ? beforeList.length : 0;

  // send malformed JSON
  const res = await request.post('/notes', {
    data: malformed,
    headers: { 'Content-Type': 'application/json' }
  });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toHaveProperty('message', 'Invalid JSON');

  // verify list unchanged
  const afterRes = await request.get('/notes');
  expect(afterRes.status()).toBe(200);
  const afterList = await afterRes.json();
  const finalCount = Array.isArray(afterList) ? afterList.length : 0;
  expect(finalCount).toBe(initialCount);
});
