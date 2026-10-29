import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-17: Notes persist across multiple restarts.

test('[AC-17] notes survive multiple restarts', async ({ request }) => {
  // Start first instance
  const svc1 = await startService();
  // Create a note
  await request.post('/notes', { data: { title: 'Persisted' } });
  await svc1.stop();

  // Restart second instance with same dataDir
  const svc2 = await startService({ dataDir: svc1.dataDir });
  const resAfterFirstRestart = await request.get('/notes');
  expect(resAfterFirstRestart.status()).toBe(200);
  const notes1 = await resAfterFirstRestart.json();
  expect(notes1.length).toBe(1);
  expect(notes1[0].title).toBe('Persisted');

  // Restart third instance
  const svc3 = await startService({ dataDir: svc2.dataDir });
  const resAfterSecondRestart = await request.get('/notes');
  expect(resAfterSecondRestart.status()).toBe(200);
  const notes2 = await resAfterSecondRestart.json();
  expect(notes2.length).toBe(1);
  expect(notes2[0].title).toBe('Persisted');

  // Clean up
  await svc3.stop();
});
