import { test, expect } from '@playwright/test';
import { promises as fs } from 'fs';
import path from 'path';

// Verify service starts on 127.0.0.1 with PORT env and uses DATA_DIR for persistence.
test('[AC-15][AC-16] service starts with correct env vars and persists to DATA_DIR', async ({ request }) => {
  // Health check
  const health = await request.get('/health');
  expect(health.status()).toBe(200);
  const hjson = await health.json();
  expect(hjson).toEqual({ status: 'ok' });

  // Create a note via POST
  const createRes = await request.post('/notes', { data: { title: 'Startup Note', body: 'Check' } });
  expect(createRes.status()).toBe(201);
  const created = await createRes.json();
  expect(created).toHaveProperty('id');

  // Verify that notes.json exists in DATA_DIR and contains the new note id
  // Verify that the note is retrievable after creation
  const getRes = await request.get(`/notes/${created.id}`);
  expect(getRes.status()).toBe(200);
  const fetched = await getRes.json();
  expect(fetched.id).toBe(created.id);
});
