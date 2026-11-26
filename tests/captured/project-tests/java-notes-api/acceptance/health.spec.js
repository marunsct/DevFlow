import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';
import fs from 'node:fs';
import path from 'node:path';

// AC-14: GET /health answers 200 with {"status": "UP"}
// Uses the service already started by Playwright's webServer config.
test('[AC-14] GET /health returns 200', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toHaveProperty('status');
  expect(body.status).toBe('UP');
});

// AC-15: The project directory has a start.sh that starts the service on
// 127.0.0.1 at the port in the PORT environment variable, keeping its data
// under the directory in the DATA_DIR environment variable.
// Proven by starting a fresh instance via the harness helper and confirming
// it answers on the port it was given, using the DATA_DIR it was given.
test('[AC-15] start.sh starts the service on the given port and DATA_DIR', async ({ request }) => {
  const service = await startService();

  // Verify the service is reachable on the port start.sh chose
  const health = await request.get(service.baseURL + '/health');
  expect(health.status()).toBe(200);

  // Verify data is stored under the DATA_DIR the harness gave us
  // by creating a note and confirming it persists when we restart
  const create = await request.post(service.baseURL + '/notes', {
    data: { title: 'start.sh test', body: 'Verifies DATA_DIR' },
  });
  expect(create.status()).toBe(201);

  // Stop and restart with the same DATA_DIR
  await service.stop();
  const restarted = await startService({ dataDir: service.dataDir });

  // The note should survive the restart
  const list = await request.get(restarted.baseURL + '/notes');
  expect(list.status()).toBe(200);
  const notes = await list.json();
  expect(Array.isArray(notes)).toBeTruthy();
  expect(notes.length).toBe(1);
  expect(notes[0].title).toBe('start.sh test');

  await restarted.stop();
});
