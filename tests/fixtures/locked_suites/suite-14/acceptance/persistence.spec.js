// This file uses the Playwright test runner but performs its own server lifecycle using the helper `startService`.
import { test, expect } from '@playwright/test';
import * as svc from './service.cjs';
const { startService } = svc;

async function postNote(baseURL, title, body) {
  const res = await fetch(`${baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, body }),
  });
  expect(res.status).toBe(201);
  return await res.json();
}

async function getNotes(baseURL) {
  const res = await fetch(`${baseURL}/notes`);
  expect(res.status).toBe(200);
  return await res.json();
}

test('[AC-6][AC-17] notes persist across restarts', async () => {
  // start first service with a temporary data directory
  const srv1 = await startService({});
  try {
    const note = await postNote(srv1.baseURL, 'Persist', 'Data');
    expect(note.title).toBe('Persist');
    // stop the first instance
    await srv1.stop();
    // restart with the same data directory to verify persistence
    const srv2 = await startService({ dataDir: srv1.dataDir });
    try {
      const notes = await getNotes(srv2.baseURL);
      expect(notes).toEqual([note]);
    } finally {
      await srv2.stop();
    }
  } finally {
    if (!srv1?.exitCode) await srv1.stop();
  }
});
