import { test, expect } from '@playwright/test';

// AC-13 & AC-18: Validation rejects missing or empty title and over‑length fields.
test('[AC-13][AC-18] validation rejects bad input', async ({ request }) => {
  // Title missing
  const resMissing = await request.post('/notes', { data: { body: 'No title' } });
  expect(resMissing.status()).toBe(422);
  const jsonMissing = await resMissing.json();
  expect(jsonMissing).toHaveProperty('error');

  // Title empty after trim
  const resEmpty = await request.post('/notes', { data: { title: '   ', body: 'Empty' } });
  expect(resEmpty.status()).toBe(422);
  const jsonEmpty = await resEmpty.json();
  expect(jsonEmpty).toHaveProperty('error');

  // Title too long (256 chars)
  const longTitle = 'a'.repeat(256);
  const resLongTitle = await request.post('/notes', { data: { title: longTitle, body: 'Long' } });
  expect(resLongTitle.status()).toBe(422);

  // Body too long (1025 chars)
  const longBody = 'b'.repeat(1025);
  const resLongBody = await request.post('/notes', { data: { title: 'Title', body: longBody } });
  expect(resLongBody.status()).toBe(422);

  // Non‑integer id on GET
  const resNonInt = await request.get('/notes/abc');
  expect(resNonInt.status()).toBe(400);
  const jsonNonInt = await resNonInt.json();
  expect(jsonNonInt).toHaveProperty('error');
});
