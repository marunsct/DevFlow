import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Helper to perform fetch against a baseURL.
async function fetchJson(url, init = {}) {
  const resp = await fetch(url, init);
  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch (_) {
    throw new Error('Response not valid JSON: ' + text);
  }
}

test('[AC-6][AC-17] notes survive and persist after service restart', async () => {
  // Start first instance, create a note.
  const first = await startService();
  const { baseURL, dataDir } = first;
  const createResp = await fetchJson(baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persisted', body: 'Keep me' }),
  });
  expect(createResp).toHaveProperty('id');
  const noteId = createResp.id;

  // Stop first instance.
  await first.stop();

  // Start second instance with same data directory.
  const second = await startService({ dataDir, timeoutMs: 60000 });
  const { baseURL: secondBase } = second;

  // Retrieve the note from the restarted service.
  const getResp = await fetchJson(secondBase + `/notes/${noteId}`);
  expect(getResp).toMatchObject({ title: 'Persisted', body: 'Keep me' });

  await second.stop();
});
