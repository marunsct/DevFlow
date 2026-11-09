import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-5] DELETE /notes/:id removes note and returns 204', async ({request})=>{
  const note = await createNote(request,'DeleteMe','Bye');
  const del = await request.delete(`/notes/${note.id}`);
  expect(del.status()).toBe(204);
});
