import { test, expect } from '@playwright/test';

async function createNote(request,title,body){const r=await request.post('/notes',{data:{title,body}});expect(r.status()).toBe(201);return (await r.json()).id;}
async function deleteNote(request,id){const res=await request.delete(`/notes/${id}`);expect(res.status()).toBe(204);} 
test('[AC-12] DELETE /notes/:id removes note and returns 204', async ({request})=>{
  const id=await createNote(request,'Temp','Del');
  const delRes=await request.delete(`/notes/${id}`);
  expect(delRes.status()).toBe(204);
  // verify not found
  const getRes=await request.get(`/notes/${id}`);expect(getRes.status()).toBe(404);
});
