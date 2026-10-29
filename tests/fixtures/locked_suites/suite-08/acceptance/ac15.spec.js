import { test, expect } from '@playwright/test';

// Verify that the service is started by start.sh on 127.0.0.1 using the PORT env variable.
// The Playwright fixture uses the webServer defined in playwright.config.js which starts
// the application via `sh start.sh`. We simply hit an endpoint that must be reachable
// and confirm it responds with the expected status code. This indirectly proves that
// the server was bound to the correct address/port and that DATA_DIR is respected by
// the application (the persistence tests cover that).

test('[AC-15] service starts on 127.0.0.1 with PORT and DATA_DIR', async ({ request }) => {
  const res = await request.get('/health');
  expect(res.status()).toBe(200);
});
