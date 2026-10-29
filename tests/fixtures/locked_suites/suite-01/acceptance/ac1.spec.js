import { test, expect } from '@playwright/test';

// AC-1: Create a note with title and body – verifies 201 response, returned JSON and Location header.

test('[AC-1] creates a note', async ({ request }) => {
  const res = await request.post('/notes', {
    data: { title: 'Test Note', body: 'Content' },
  });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(typeof json.id).toBe('number');
  expect(json.title).toBe('Test Note');
  expect(json.body).toBe('Content');
  // Location header should point to the new resource
  const location = res.headers()['location'];
  expect(location).toMatch(/^\/notes\/[0-9]+$/);
});
