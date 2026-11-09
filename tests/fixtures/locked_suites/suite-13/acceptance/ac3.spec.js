import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-3] GET /notes/:id returns note or 404 when missing', async ({request})=>{
  const note = await createNote(request,'Solo','Only');
  const res = await request.get(`/notes/${note.id}`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual(note);
  const miss = await request.get('/notes/9999');
  expect(miss.status()).toBe(404);
});
