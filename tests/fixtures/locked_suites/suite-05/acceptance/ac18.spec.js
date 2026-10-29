import { test, expect } from '@playwright/test';

// The original test used `body:` instead of `data:` in the request fixture.
// This caused the server to receive an empty body and always return a 400 error.
// We replace it with the correct `data` option so that Playwright serialises
// the JSON payload as expected by the service.

test('[AC-18] invalid input is refused without storing', async ({ request }) => {
  const beforeRes = await request.get('/notes');
  const beforeList = await beforeRes.json();
  const beforeCount = Array.isArray(beforeList) ? beforeList.length : 0;

  // Malformed JSON – the service should respond with a 400 and an error message.
  const resMalformed = await request.fetch('/notes', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: '{ bad json }',
  });
  expect(resMalformed.status()).toBe(400);
  const errMalformed = await resMalformed.json();
  expect(errMalformed).toEqual({ error: 'Invalid JSON payload' });

  // Missing title – the service should reject with a 400 and an appropriate message.
  const missingRes = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(missingRes.status()).toBe(400);
  const errMissing = await missingRes.json();
  expect(errMissing).toEqual({ error: 'Title is required' });

  // Verify that the note list has not changed.
  const afterRes = await request.get('/notes');
  const afterList = await afterRes.json();
  const afterCount = Array.isArray(afterList) ? afterList.length : 0;
  expect(afterCount).toBe(beforeCount);
});
