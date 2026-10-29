import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import path from 'path';
import fs from 'fs';
import os from 'os';

// Helper to wait for service to be up
async function waitUntilUp(url, child, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error('service exited with code ' + child.exitCode);
    try {
      await fetch(url + '/health');
      return;
    } catch {}
    await new Promise((r)=>setTimeout(r,200));
  }
  throw new Error('service did not answer within ' + timeoutMs + ' ms');
}

test('[AC-15] start.sh starts service on 127.0.0.1 with PORT and uses DATA_DIR', async ({}) => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'notes-api-test-'));
  const port = 12345; // deterministic test port
  const child = spawn('node', ['src/main.ts'], {
    cwd: path.resolve(process.cwd()),
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', DATA_DIR: tmpDir },
    stdio: ['ignore', 'pipe', 'inherit'],
  });

  let stdout = '';
  child.stdout.on('data', (chunk)=>{stdout += chunk.toString();});

  await waitUntilUp(`http://127.0.0.1:${port}`, child, 5000);

  const resHealth = await fetch(`http://127.0.0.1:${port}/health`);
  expect(resHealth.status).toBe(200);
  const jsonHealth = await resHealth.json();
  expect(jsonHealth).toEqual({ status: 'ok' });

  const noteRes = await fetch(`http://127.0.0.1:${port}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Test', body: 'Body' }),
  });
  expect(noteRes.status).toBe(201);

  const notesFile = path.join(tmpDir, 'notes.json');
  await new Promise(r=>setTimeout(r,100));
  expect(fs.existsSync(notesFile)).toBe(true);

  child.kill();
});
