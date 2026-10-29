import { test, expect } from '@playwright/test';

import { startService } from './service.cjs';

async function createNote(baseURL, title) {
  const res = await fetch(`${baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  expect(res.status).toBe(201);
  return await res.json();
}

async function listNotes(baseURL) {
  const res = await fetch(`${baseURL}/notes`);
  expect(res.status).toBe(200);
  return await res.json();
}

test('[AC-6] notes survive a restart of the service', async () => {
  const first = await startService();
  try {
    const created = await createNote(first.baseURL, 'PersistTest');
    await first.stop();
    const second = await startService({ dataDir: first.dataDir });
    try {
      const notes = await listNotes(second.baseURL);
      expect(notes).toHaveLength(1);
      expect(notes[0]).toEqual(created);
    } finally { await second.stop(); }
  } finally { if (first.exitCode === null) await first.stop(); }
});

test('[AC-17] id increments correctly after a restart', async () => {
  const svc = await startService();
  try {
    const note1 = await createNote(svc.baseURL, 'First');
    const note2 = await createNote(svc.baseURL, 'Second');
    const maxId = Math.max(note1.id, note2.id);
    await svc.stop();

    const svc2 = await startService({ dataDir: svc.dataDir });
    try {
      const newNote = await createNote(svc2.baseURL, 'Third');
      expect(newNote.id).toBe(maxId + 1);
    } finally { await svc2.stop(); }
  } finally { if (svc.exitCode === null) await svc.stop(); }
});
