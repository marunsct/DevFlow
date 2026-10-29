import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-16] All endpoints respond with correct status codes', async ({request})=>{
  // health
  const h = await request.get('/health');
  expect(h.ok()).toBeTruthy();
  // create
  const note = await createNote(request);
  // list
  const l = await request.get('/notes');
  expect(l.status()).toBe(200);
  // get
  const g = await request.get(`/notes/${note.id}`);
  expect(g.status()).toBe(200);
  // update
  const u = await request.put(`/notes/${note.id}`,{data:{title:'Upd',body:'B'}});
  expect(u.status()).toBe(200);
  // delete
  const d = await request.delete(`/notes/${note.id}`);
  expect(d.status()).toBe(204);
});
