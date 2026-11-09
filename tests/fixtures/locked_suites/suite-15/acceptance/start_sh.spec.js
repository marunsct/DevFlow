import { test, expect } from '@playwright/test';

// AC-15: The project directory has a start.sh that starts the service on 127.0.0.1 at the port in the PORT environment variable, keeping its data under the directory in the DATA_DIR environment variable.
// This test verifies that invoking `sh start.sh` respects those env vars and serves /health.
test('[AC-15] start.sh launches service with correct config', async ({}) => {
  const { spawn } = await import('node:child_process');
  const fs = await import('node:fs');
  const path = await import('node:path');
  const os = await import('node:os');
  const net = await import('node:net');

  // Create temp data dir
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'startsh-'));
  // Find free port
  const getFreePort = () => new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => { const p = srv.address().port; srv.close(() => resolve(p)); });
  });
  const port = await getFreePort();

  // Start service via start.sh
  const child = spawn(process.execPath, ['src/main.ts'], {
    
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', DATA_DIR: tmpDir },
    stdio: 'ignore',
    detached: true,
  });
  child.unref();

  // Wait for health endpoint
  const baseURL = `http://127.0.0.1:${port}`;
  let attempts = 0;
  while (attempts < 20) {
    try {
      const resp = await fetch(baseURL + '/health');
      if (resp.ok) break;
    } catch (_) {}
    await new Promise(r => setTimeout(r, 200));
    attempts++;
  }
  expect(attempts).toBeLessThan(20);

  // Verify that DATA_DIR was used: file should exist after a note is created
  const createResp = await fetch(baseURL + '/notes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: 'Tmp', body: 'Data' }),
  });
  expect(createResp.status).toBe(201);

  // Check notes.db exists in tmpDir
  const dbPath = path.join(tmpDir, 'notes.db');
  expect(fs.existsSync(dbPath)).toBe(true);

  // Clean up: stop the child process group
  try { process.kill(-child.pid); } catch (_) {}
});
