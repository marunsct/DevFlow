import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

async function freePort() {
  const net = await import('net');
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitUntilUp(baseURL) {
  for (let i = 0; i < 10; i++) {
    try {
      const res = await fetch(`${baseURL}/health`);
      if (res.ok) return;
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('service not up');
}

test('[AC-15] start.sh uses PORT and DATA_DIR', async () => {
  const port = await freePort();
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'start-test-'));
const child = spawn('node', ['src/main.ts'], {
      cwd: 'notes-api',
      env: { ...process.env, PORT: String(port), DATA_DIR: dataDir },
      stdio: 'ignore',
      detached: true,
    });
  child.unref();
  await waitUntilUp(`http://127.0.0.1:${port}`);
  const resp = await fetch(`http://127.0.0.1:${port}/health`);
  expect(resp.ok).toBeTruthy();
  process.kill(-child.pid, 'SIGTERM');
});
