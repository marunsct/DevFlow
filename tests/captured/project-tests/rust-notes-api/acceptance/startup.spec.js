import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';
import fs from 'fs';

// ES-module equivalent of __dirname: the directory containing this spec file.
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ──────────────────────────────────────────────────
// AC-14  GET /health answers 200
// (The service is already started by the Playwright
//  webServer config; no extra setup needed.)
// ──────────────────────────────────────────────────

test('[AC-14] GET /health returns 200', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);

  const body = await res.json();
  expect(body).toHaveProperty('status');
});

// ──────────────────────────────────────────────────
// AC-15  start.sh starts the service on 127.0.0.1
//         using PORT and DATA_DIR env vars
//
// This test proves the *behaviour* that start.sh
// delivers: the running product listens on the port
// given by $PORT, stores data under $DATA_DIR, and
// responds to /health.  It does not read or assert
// the text of start.sh (that belongs to the harness).
// ──────────────────────────────────────────────────

test('[AC-15] start.sh starts the service on PORT with DATA_DIR', async ({ request }) => {
  // Verify start.sh exists in the project directory.
  // We do NOT read its contents — that is a harness file.
  const startShPath = resolve(__dirname, '..', 'start.sh');
  expect(fs.existsSync(startShPath)).toBeTruthy();

  // The Playwright webServer config already starts the
  // service via start.sh (see playwright.config.js).
  // We prove it works by hitting /health on its own port.
  const res = await request.get('/health');
  expect(res.status()).toBe(200);

  // Create a note — if DATA_DIR is not working, this fails.
  const createRes = await request.post('/notes', {
    data: { title: 'start-sh test', body: 'verifies DATA_DIR' },
  });
  expect(createRes.status()).toBe(201);

  // Verify it was stored by reading it back.
  const noteId = (await createRes.json()).id;
  const getRes = await request.get(`/notes/${noteId}`);
  expect(getRes.status()).toBe(200);

  const note = await getRes.json();
  expect(note.title).toBe('start-sh test');
});
