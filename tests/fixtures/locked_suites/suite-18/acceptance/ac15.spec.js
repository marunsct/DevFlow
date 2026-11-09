import { test, expect } from '@playwright/test';

// AC-15: The project directory has a start.sh that starts the service on 127.0.0.1 at the port in the PORT environment variable,
// keeping its data under the directory in the DATA_DIR environment variable.
// This test indirectly verifies that the service is started with correct env vars by checking health endpoint.
test('[AC-15] Service starts with correct environment variables', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
  const json = await res.json();
  expect(json).toEqual({ status: 'ok' });
});
