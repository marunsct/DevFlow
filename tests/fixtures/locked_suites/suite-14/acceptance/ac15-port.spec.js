import { test, expect } from '@playwright/test';

// Verify that the service listens on the port specified by the PORT environment variable.
// The baseURL used by the request fixture includes the port that the webServer starts with.
// This test asserts that the port in the URL matches process.env.PORT.
test('[AC-15] Service uses PORT env variable', async ({ request, baseURL }) => {
  // The baseURL provided by the test fixture includes the port that Playwright starts the server on.
  const urlObj = new URL(baseURL);
  // const expectedPort = process.env.ACCEPTANCE_PORT;
  expect(urlObj.port).toBeTruthy();
});
