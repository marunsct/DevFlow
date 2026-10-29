import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-18: Invalid input is refused without storing anything.

test('[AC-18] invalid update not stored', async () => {
  const svc = await startService();
  // Create a valid note first
  const createRes = await fetch(`${svc.baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Valid' }),
  });
  expect(createRes.status).toBe(201);
  const created = await createRes.json();

  // Attempt invalid update with empty title
  const putRes = await fetch(`${svc.baseURL}/notes/${created.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: '', body: 'No' }),
  });
  expect(putRes.status).toBe(400);

  // Ensure note unchanged
  const getRes = await fetch(`${svc.baseURL}/notes/${created.id}`);
  const fetched = await getRes.json();
  expect(fetched.title).toBe('Valid');
  await svc.stop();
});
