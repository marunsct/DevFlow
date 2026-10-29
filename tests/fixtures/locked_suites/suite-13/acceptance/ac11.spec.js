import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-11] PUT /notes/:id updates note and returns updated note or 404', async ({request})=>{
  const note = await createNote(request,'Old','Body');
  const updResp = await request.put(`/notes/${note.id}`,{data:{title:'New',body:'Changed'}});
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated.title).toBe('New');
  expect(updated.body).toBe('Changed');
  const get = await request.get(`/notes/${note.id}`);
  expect((await get.json()).title).toBe('New');
});
