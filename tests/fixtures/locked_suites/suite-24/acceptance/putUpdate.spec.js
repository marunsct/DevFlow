import { test, expect } from '@playwright/test';

async function createNote(request,title,body){const res=await request.post('/notes',{data:{title,body}});expect(res.status()).toBe(201);return (await res.json()).id;}
async function deleteNote(request,id){const r=await request.delete(`/notes/${id}`);expect(r.status()).toBe(204);} 
test('[AC-11] PUT /notes/:id updates note and returns 200', async ({request})=>{
  const id=await createNote(request,'Old','Body');
  const resPut=await request.put(`/notes/${id}`,{data:{title:'New',body:'Updated'}});
  expect(resPut.status()).toBe(200);
  const updated=(await resPut.json());
  expect(updated).toEqual({id,title:'New',body:'Updated'});
  // verify GET reflects update
  const resGet=await request.get(`/notes/${id}`);const got=await resGet.json();expect(got).toEqual(updated);
  await deleteNote(request,id);
});
