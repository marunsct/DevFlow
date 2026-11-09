import { test, expect } from '@playwright/test';

const { startService } = await import('./service.cjs');

async function fetchReq(baseURL, method, path, body) {
  const res = await fetch(`${baseURL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, json: () => res.json() };
}

test('[AC-6][AC-17] Notes survive a service restart', async () => {
  const first = await startService();
  const base1 = first.baseURL;

  // Create a note.
  await fetchReq(base1, 'POST', '/notes', { title: 'Persisted', body: 'Data' });
  await first.stop();

  const second = await startService({ dataDir: first.dataDir });
  const base2 = second.baseURL;
  const listRes = await fetchReq(base2, 'GET', '/notes');
  expect(listRes.status).toBe(200);
  const list = await listRes.json();
  expect(list.length).toBeGreaterThan(0);
  expect(list[0].title).toBe('Persisted');
  await second.stop();
});
