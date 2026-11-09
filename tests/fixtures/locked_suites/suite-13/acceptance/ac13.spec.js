import { test, expect } from '@playwright/test';

async function createNote(request,title='Test',body='Body'){
  const resp = await request.post('/notes',{data:{title,body}});
  return await resp.json();
}

test('[AC-13] missing or empty title results in error and no persistence', async ({request})=>{
  // Empty title after trim – should return 422
  const emptyResp = await request.post('/notes',{data:{title:'   ',body:'Empty'}});
  expect(emptyResp.status()).toBe(422);
  expect(await emptyResp.json()).toEqual({error:'Title required'});

  // Missing title field – should return 400
  const missingResp = await request.post('/notes',{data:{body:'No title'}});
  expect(missingResp.status()).toBe(400);
  expect(await missingResp.json()).toEqual({error:'Title required'});

  // Ensure no note was stored: list notes and verify titles are absent
  const listResp = await request.get('/notes');
  const notes = await listResp.json();
  expect(notes).not.toContainEqual(expect.objectContaining({title:'   '}));
  expect(notes).not.toContainEqual(expect.objectContaining({title:'No title'}));
});
