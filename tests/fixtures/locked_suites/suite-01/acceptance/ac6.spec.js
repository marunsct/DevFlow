import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-6: notes survive a restart

test('[AC-6] notes survive a restart', async () => {
  const svc1 = await startService();
  await fetch(`${svc1.baseURL}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Persisted' })
  });
  await svc1.stop();

  const svc2 = await startService({ dataDir: svc1.dataDir });
  const resAfterFirstRestart = await fetch(`${svc2.baseURL}/notes`);
  expect(resAfterFirstRestart.status).toBe(200);
  const notes1 = await resAfterFirstRestart.json();
  expect(notes1.length).toBe(1);
  expect(notes1[0].title).toBe('Persisted');

  const svc3 = await startService({ dataDir: svc2.dataDir });
  const resAfterSecondRestart = await fetch(`${svc3.baseURL}/notes`);
  expect(resAfterSecondRestart.status).toBe(200);
  const notes2 = await resAfterSecondRestart.json();
  expect(notes2.length).toBe(1);
  expect(notes2[0].title).toBe('Persisted');

  await svc3.stop();
});
