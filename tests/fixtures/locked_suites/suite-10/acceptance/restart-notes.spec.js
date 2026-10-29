import { test, expect } from '@playwright/test';

// [AC-6][AC-17] notes survive a restart of the service
test('[AC-6][AC-17] notes persist after server restart', async () => {
  const service = await import('./service.cjs');
  // first run
  const svc1 = await service.startService();
  const payload = { title: 'Persist', body: 'Keep' };
  await fetch(svc1.baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  // stop first
  await svc1.stop();
  // second run with same dataDir
  const svc2 = await service.startService({ dataDir: svc1.dataDir });
  const res = await fetch(svc2.baseURL + '/notes');
  expect(res.status).toBe(200);
  const notes = await res.json();
  expect(notes.length).toBeGreaterThan(0);
  const found = notes.find(n => n.title === payload.title && n.body === payload.body);
  expect(found).not.toBeUndefined();
});
