import { test, expect } from '@playwright/test';

// Test that responses (except 204) include Content-Type: application/json
test('[AC-7] response includes JSON content type', async ({ request }) => {
  const res = await request.get('/notes');
  const ct = res.headers()['content-type'];
  expect(ct).toContain('application/json');
});

// Test unsupported media type for POST and PUT
const nonJsonHeaders = { 'Content-Type': 'text/plain' };
    test('[AC-18] POST with non‑JSON content type returns 415', async ({ request }) => {
      const res = await request.post('/notes', {
        data: 'plain text',
        headers: nonJsonHeaders,
      });
      expect(res.status()).toBe(415);
    const err = await res.json();
    expect(err).toEqual({ error: 'Unsupported media type' });

    });

test('[AC-18] PUT with non‑JSON content type returns 415', async ({ request }) => {
  // first create a note
  const postRes = await request.post('/notes', { data: { title: 'A', body: 'B' } });
  const id = (await postRes.json()).id;
  const res = await request.put(`/notes/${id}`, {
    data: 'plain text',
    headers: nonJsonHeaders,
  });
  expect(res.status()).toBe(415);
  const err = await res.json();
  expect(err).toEqual({ error: 'Unsupported media type' });
});

// Test title length >255 bytes is rejected
const longTitle = 'a'.repeat(256);
test('[AC-18] POST with too long title returns 400', async ({ request }) => {
  const res = await request.post('/notes', { data: { title: longTitle, body: 'B' } });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title too long or invalid' });
});

// Test that a non‑JSON body is rejected even if content type correct
const badJson = '{ title: "x" }'; // malformed JSON
const goodHeader = { 'Content-Type': 'application/json' };
test('[AC-18] POST with malformed JSON returns 400', async ({ request }) => {
  const res = await request.post('/notes', {
    headers: goodHeader,
    data: badJson, // note: request fixture will send string as body
  });
  expect(res.status()).toBe(400);
  const err = await res.json();
  expect(err).toEqual({ error: 'Title required' } /* title missing due to parse fail */ );
});
