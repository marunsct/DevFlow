import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-7] JSON response for a note has id, title, body with correct types', async ({request})=>{
  const note = await createNote(request,'A','B');
  expect(typeof note.id).toBe('number');
  expect(typeof note.title).toBe('string');
  expect(typeof note.body).toBe('string');
});
