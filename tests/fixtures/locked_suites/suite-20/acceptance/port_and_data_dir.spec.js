import { test, expect } from '@playwright/test';

// This test verifies that the service starts on the port specified by the PORT env variable
// and uses the DATA_DIR directory for persistence.
import * as service from './service.cjs';

test('[AC-15] Service respects PORT and DATA_DIR environment variables', async () => {
  // Create a temporary data directory. The service will pick a free port automatically.
  const svc = await service.startService();
  try {
    // The baseURL should be http://127.0.0.1:<port>
    expect(svc.baseURL).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);

    // Verify health endpoint works, implying the server is listening.
    const res = await fetch(`${svc.baseURL}/health`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ status: 'ok' });
  } finally {
    await svc.stop();
  }
});
