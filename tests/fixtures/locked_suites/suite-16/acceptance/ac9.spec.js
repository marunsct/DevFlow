import { test, expect } from '@playwright/test';

// Test AC-9: GET /notes returns all notes
// This test creates two notes and verifies the list contains them.
test('[AC-9] GET /notes returns all notes', async ({ request }) => {
  const create = async (title, body) => {
    const res = await request.post('/notes', { data: { title, body } });
    expect(res.status()).toBe(201);
    return (await res.json()).id;
  };
  const idA = await create('A', 'a');
  const idB = await create('B', 'b');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const notes = await res.json();
  expect(Array.isArray(notes)).toBe(true);
  const ids = notes.map(n => n.id);
  expect(ids).toContain(idA);
  expect(ids).toContain(idB);
});
