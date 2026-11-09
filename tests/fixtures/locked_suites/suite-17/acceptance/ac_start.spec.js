import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs/promises';

// Helper to wait until the health endpoint responds
async function waitUntilHealthy(baseURL, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseURL}/health`);
      if (res.ok) return;
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('Health endpoint did not become ready');
}

// Test that start.sh starts the service on 127.0.0.1 with PORT and DATA_DIR env vars
test('[AC-15] start.sh launches service on 127.0.0.1 using PORT and DATA_DIR', async () => {
  const tmpDir = await fs.mkdtemp(path.join(process.env.TMPDIR || '/tmp', 'service-data-'));
  const port = 40000 + Math.floor(Math.random() * 1000);

  const env = { ...process.env, PORT: String(port), HOST: '127.0.0.1', DATA_DIR: tmpDir };
  const proc = spawn('sh', ['start.sh'], {
    cwd: process.cwd(),
    env,
    stdio: ['ignore', 'inherit', 'inherit'],
  });

  // Ensure process starts and is still running after health check
  try {
    const baseURL = `http://127.0.0.1:${port}`;
    await waitUntilHealthy(baseURL);
    // Simple health request to confirm endpoint works
    const res = await fetch(`${baseURL}/health`);
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ status: 'ok' });
  } finally {
    // Clean up process
    if (!proc.killed) proc.kill('SIGTERM');
    // Wait for exit
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
});
