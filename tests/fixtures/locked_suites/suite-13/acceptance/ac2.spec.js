import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  expect(resp.status()).toBe(201);
  return await resp.json();
}

test('[AC-2] GET /notes lists all created notes', async ({request})=>{
  const a = await createNote(request,'A','a');
  const b = await createNote(request,'B','b');
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  const ids=list.map(n=>n.id);
  expect(ids).toContain(a.id);
  expect(ids).toContain(b.id);
});
