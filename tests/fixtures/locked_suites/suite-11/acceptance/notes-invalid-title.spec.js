import { test, expect } from '@playwright/test';

// AC-13: POST /notes with missing or empty title returns 400 and nothing is stored
const jsonBody = (body) => ({ data: body });

test('[AC-13] POST /notes without a title returns 400 and does not create a note', async ({ request }) => {
  // ensure starting list is empty
  const beforeRes = await request.get('/notes');
  expect(beforeRes.status()).toBe(200);
  const beforeList = await beforeRes.json();
  const initialCount = Array.isArray(beforeList) ? beforeList.length : 0;

  // attempt to create without title
  const res = await request.post('/notes', jsonBody({ body: 'No title here' }));
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toHaveProperty('message', 'Title is required');

  // verify list unchanged
  const afterRes = await request.get('/notes');
  expect(afterRes.status()).toBe(200);
  const afterList = await afterRes.json();
  const finalCount = Array.isArray(afterList) ? afterList.length : 0;
  expect(finalCount).toBe(initialCount);
});
