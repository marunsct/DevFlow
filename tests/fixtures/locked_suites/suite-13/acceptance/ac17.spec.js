import { test, expect } from '@playwright/test';

// Test persistence across restart using the harness helper
test('[AC-17] Notes persist after server restart', async () => {
  const { startService } = await import('./service.cjs');
  // first instance
  const first = await startService();
  const resp = await fetch(`${first.baseURL}/notes`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Persist','body':'Data'})
  });
  expect(resp.status).toBe(201);
  const created = await resp.json();
  // stop
  await first.stop();
  // second instance same dataDir
  const second = await startService({dataDir:first.dataDir});
  const getResp = await fetch(`${second.baseURL}/notes/${created.id}`);
  expect(getResp.status).toBe(200);
  const got = await getResp.json();
  expect(got.title).toBe('Persist');
  expect(got.body).toBe('Data');
  await second.stop();
});
