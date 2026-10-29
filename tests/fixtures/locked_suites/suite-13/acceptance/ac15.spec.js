import { test, expect } from '@playwright/test';

// Test that the service can be started via start.sh and responds to /health
test('[AC-15] Service starts with start.sh and exposes health endpoint', async () => {
  const { startService } = await import('./service.cjs');
  const svc = await startService();
  const resp = await fetch(`${svc.baseURL}/health`);
  expect(resp.ok).toBeTruthy();
  const json = await resp.json();
  expect(json).toEqual({ status: 'ok' });
  await svc.stop();
});
