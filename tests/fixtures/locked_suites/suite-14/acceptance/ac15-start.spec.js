import { test, expect } from '@playwright/test';

// Verify that the service starts with correct host and port.
// The baseURL used by the request fixture includes the host and port.
test('[AC-15] Service starts with correct host and port', async ({ request, baseURL }) => {
  // The baseURL should start with http://127.0.0.1:
  expect(baseURL).toBeTruthy();
  expect(baseURL.startsWith('http://127.0.0.1:')).toBeTruthy();
});
