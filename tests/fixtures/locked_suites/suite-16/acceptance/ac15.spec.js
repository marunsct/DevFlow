import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

// Test AC-15: service uses DATA_DIR for persistence and starts on correct port
// This test creates a note, reads the notes.json file in the DATA_DIR directory,
// and verifies that the note is present. The port used by the server is
// implicitly verified by the request fixture.
test('[AC-15] Service persists data in DATA_DIR', async ({ request }) => {
  const create = async (title, body) => {
    const res = await request.post('/notes', { data: { title, body } });
    expect(res.status()).toBe(201);
    return (await res.json());
  };
  const note = await create('Persist', 'Data');

  // DATA_DIR is set by the test harness; read the file directly.
  const dataDir = process.env.DATA_DIR || path.join(process.cwd(), 'data');
  const filePath = path.join(dataDir, 'notes.json');
  const raw = fs.readFileSync(filePath, 'utf8');
  const state = JSON.parse(raw);
  expect(state.notes).toBeInstanceOf(Array);
  const stored = state.notes.find(n => n.id === note.id);
  expect(stored).toEqual(note);
});
