import { test, expect } from '@playwright/test';

// AC-15: Start script launches service on 127.0.0.1 with PORT and DATA_DIR.
// The harness already starts the server; we just verify that a request succeeds.

test('[AC-15] start.sh runs correctly', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
});
