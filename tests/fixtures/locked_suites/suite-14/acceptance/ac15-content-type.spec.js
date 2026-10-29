import { test, expect } from '@playwright/test';

// Verify that all responses have Content-Type: application/json.
// Test a POST and a GET for the notes resource.

test('[AC-15] Response headers include Content-Type: application/json', async ({ request }) => {
  // Create a note to get a valid ID for subsequent GET
  const createRes = await request.post('/notes', { data: { title: 'Header Test', body: 'Body' } });
  expect(createRes.status()).toBe(201);
  const json = await createRes.json();
  const id = json.id;

  // Check header on POST response
  const postHeaders = createRes.headers();
  expect(postHeaders['content-type']).toContain('application/json');

  // GET the note
  const getRes = await request.get(`/notes/${id}`);
  expect(getRes.status()).toBe(200);
  const getHeaders = getRes.headers();
  expect(getHeaders['content-type']).toContain('application/json');
});
