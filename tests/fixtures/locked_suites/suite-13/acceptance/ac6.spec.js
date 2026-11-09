import { test, expect } from '@playwright/test';

// Simple health check
test('[AC-6] GET /health returns 200', async ({request})=>{
  const res = await request.get('/health');
  expect(res.ok()).toBeTruthy();
  expect(await res.json()).toEqual({ status: 'ok' });
});
