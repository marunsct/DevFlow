import { test, expect } from '@playwright/test';

// Helper to create note via fetch
async function postNote(url,title){
  const resp = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});
  return resp;
}

test('[AC-18] title longer than 255 characters is refused and not stored', async () => {
  const { startService } = await import('./service.cjs');
  const svc = await startService();
  const longTitle = 'a'.repeat(256);
  const resp = await postNote(`${svc.baseURL}/notes`,longTitle);
  expect(resp.status).toBe(422);
  const body = await resp.json();
  expect(body).toEqual({error:'Title too long'});
  // ensure no note stored
  const listResp = await fetch(`${svc.baseURL}/notes`);
  const list = await listResp.json();
  expect(list.find(n=>n.title===longTitle)).toBeUndefined();
  await svc.stop();
});
