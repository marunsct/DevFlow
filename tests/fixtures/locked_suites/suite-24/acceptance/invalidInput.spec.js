import { test, expect } from '@playwright/test';

async function createNote(request,title,body){const r=await request.post('/notes',{data:{title,body}});expect(r.status()).toBe(201);return (await r.json()).id;}
async function deleteNote(request,id){const r=await request.delete(`/notes/${id}`);expect(r.status()).toBe(204);} 

// Helper to get current count
async function noteCount(request){const res=await request.get('/notes');const list=await res.json();return Array.isArray(list)?list.length:0;}

test('[AC-18] body too large is refused without storing', async ({request})=>{
  const initial = await noteCount(request);
  // create a payload >10KB
  const bigBody = 'x'.repeat(11 * 1024); // 11 KB
  const res = await request.post('/notes',{data:{title:'Big','body':bigBody}});
  expect(res.status()).toBe(413);
  const json=await res.json();expect(json).toHaveProperty('error');
  const after = await noteCount(request);
  expect(after).toBe(initial); // no new note
});

test('[AC-18] missing title is refused without storing', async ({request})=>{
  const initial = await noteCount(request);
  const res=await request.post('/notes',{data:{body:'NoTitle'}});
  expect(res.status()).toBe(400);
  const json=await res.json();expect(json).toHaveProperty('error');
  const after=await noteCount(request);
  expect(after).toBe(initial);
});
