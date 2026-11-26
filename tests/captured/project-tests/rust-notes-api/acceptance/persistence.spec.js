import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// ──────────────────────────────────────────────────
// AC-6   Notes survive a restart of the service
// AC-17  Notes persist across restarts
//
// Uses the harness helper `startService` to:
//   1. Start the service on a free port with a fresh DATA_DIR
//   2. Create notes via POST /notes (extracting ids)
//   3. Stop the service
//   4. Restart it with the *same* DATA_DIR
//   5. Verify GET /notes returns all previously created notes
//
// Every other test uses the request fixture against the
// single service started by playwright.config.js; only
// this criterion needs its own lifecycle because it must
// stop and restart the server to prove persistence.
// ──────────────────────────────────────────────────

test('[AC-6][AC-17] Notes persist across a service restart', async ({ request }) => {
  // --- Phase 1: start, create notes, stop ---
  const first = await startService();

  // Create three distinct notes so we can verify all survive
  const noteIds = [];
  for (let i = 1; i <= 3; i++) {
    const res = await request.post(first.baseURL + '/notes', {
      data: { title: `persist-note-${i}`, body: `body-${i}` },
    });
    expect(res.status()).toBe(201);
    noteIds.push((await res.json()).id);
  }

  // Verify they are all present before stopping
  const beforeList = await request.get(first.baseURL + '/notes');
  expect(beforeList.status()).toBe(200);
  const beforeNotes = await beforeList.json();
  expect(beforeNotes.length).toBe(3);

  // Stop the service cleanly
  await first.stop();

  // --- Phase 2: restart with same DATA_DIR, verify persistence ---
  const second = await startService({ dataDir: first.dataDir });

  // Fetch all notes — they should still be there
  const afterList = await request.get(second.baseURL + '/notes');
  expect(afterList.status()).toBe(200);
  const afterNotes = await afterList.json();
  expect(afterNotes.length).toBe(3);

  // Each persisted note has the correct fields and values
  const persistedIds = afterNotes.map((n) => n.id).sort((a, b) => a - b);
  expect(persistedIds).toEqual(noteIds.sort((a, b) => a - b));

  for (const note of afterNotes) {
    expect(Object.keys(note)).toEqual(['id', 'title', 'body']);
  }

  // Verify we can still read individual notes by id
  for (const id of noteIds) {
    const getRes = await request.get(second.baseURL + `/notes/${id}`);
    expect(getRes.status()).toBe(200);
    const n = await getRes.json();
    expect(n.id).toBe(id);
  }

  // Stop the second instance
  await second.stop();
});
