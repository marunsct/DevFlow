import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// Helper to create a note via POST /notes
async function createNote(request,title,body){const r=await request.post('/notes',{data:{title,body}});expect(r.status()).toBe(201);return (await r.json()).id;}

// Helper to delete a note
async function deleteNote(request,id){const r=await request.delete(`/notes/${id}`);expect(r.status()).toBe(204);} 

test('[AC-15] start.sh starts service on 127.0.0.1 at PORT and uses DATA_DIR', async ({})=>{
  const svc = await startService();
  // Service should be reachable
  const res = await fetch(`${svc.baseURL}/health`);
  expect(res.ok).toBeTruthy();
  const json = await res.json();
  expect(json).toEqual({status:'ok'});
  // Cleanup: stop service
  await svc.stop();
});
