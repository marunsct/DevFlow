import { test, expect } from '@playwright/test';

// AC-2: List all notes
// Create two distinct notes and verify the list contains both in ascending id order.
test('[AC-2][AC-9] GET /notes returns all created notes', async ({ request }) => {
  // Create first note
  const res1 = await request.post('/notes', { data: { title: 'One', body: 'First' } });
  const n1 = await res1.json();
  expect(res1.status()).toBe(201);
  // Create second note
  const res2 = await request.post('/notes', { data: { title: 'Two', body: 'Second' } });
  const n2 = await res2.json();
  expect(res2.status()).toBe(201);
  // Get list
  const listRes = await request.get('/notes');
  expect(listRes.status()).toBe(200);
  const list = await listRes.json();
  expect(Array.isArray(list)).toBeTruthy();
  // Expect exactly two items and order by id ascending
  expect(list.length).toBeGreaterThanOrEqual(2);
  const ids = list.map(l=>l.id);
    expect(ids).toContain(n1.id);
  expect(ids).toContain(n2.id);
});
