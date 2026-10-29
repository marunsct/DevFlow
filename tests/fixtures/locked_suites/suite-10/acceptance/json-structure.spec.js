import { test, expect } from '@playwright/test';

// [AC-7] JSON structure of a note
// Verifies that a created note has id:number, title:string, body:string.
test('[AC-7] note JSON structure', async ({ request }) => {
  const payload = { title: 'Struct', body: 'Check' };
  const res = await request.post('/notes', { data: payload });
  expect(res.status()).toBe(201);
  const note = await res.json();
  expect(note).toHaveProperty('id');
  expect(typeof note.id).toBe('number');
  expect(note).toHaveProperty('title', payload.title);
  expect(note).toHaveProperty('body', payload.body);
});
