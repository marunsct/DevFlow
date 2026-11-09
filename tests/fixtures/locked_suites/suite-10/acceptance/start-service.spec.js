import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

// [AC-15] start.sh starts service on 127.0.0.1 with PORT and DATA_DIR
test('[AC-15] start.sh starts service on 127.0.0.1 with PORT and DATA_DIR', async () => {
  const service = await import('./service.cjs');
  const { startService } = await service;
  const svc = await startService();
  // baseURL should be http://127.0.0.1:<port>
  expect(svc.baseURL).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
  // dataDir should exist
  const dirExists = fs.existsSync(svc.dataDir);
  expect(dirExists).toBeTruthy();
  // notes.db file should be present in dataDir
  // Trigger DB initialization by creating a note
  await fetch(svc.baseURL + '/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'dummy' })
  });
  const dbPath = path.join(svc.dataDir, 'notes.db');
  const dbExists = fs.existsSync(dbPath);
  expect(dbExists).toBeTruthy();
  await svc.stop();
});
