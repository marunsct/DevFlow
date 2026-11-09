import { test, expect } from '@playwright/test';

async function loadStartService() {
  const mod = await import(new URL('./service.cjs', import.meta.url));
  return mod.startService;
}

test('[AC-17] notes persist across restart', async () => {
  const startService = await loadStartService();
  const first = await startService();
  // create a note
  const res1 = await fetch(first.baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persisted', body: 'Data' }),
  });
  expect(res1.status).toBe(201);
  const created = await res1.json();
  await first.stop();

  // restart with same data dir
  const second = await startService({ dataDir: first.dataDir });
  const listRes = await fetch(second.baseURL + '/notes');
  expect(listRes.status).toBe(200);
  const list = await listRes.json();
  const found = list.find((n) => n.id === created.id);
  expect(found).not.toBeUndefined();
  expect(found.title).toBe('Persisted');
  await second.stop();
});
