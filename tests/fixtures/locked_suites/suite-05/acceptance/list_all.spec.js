import { test, expect } from '@playwright/test';

async function clearAllNotes(request){const res=await request.get('/notes');if(res.status()!==200)return;const notes=await res.json();for(const n of notes)await request.delete(`/notes/${n.id}`);}
// AC-9: GET /notes returns array of all notes.
test('[AC-9] GET /notes answers 200 with a JSON array of every note', async ({request})=>{await clearAllNotes(request);const a=await request.post('/notes',{data:{title:'A',body:'a'}});const b=await request.post('/notes',{data:{title:'B',body:'b'}});const res=await request.get('/notes');expect(res.status()).toBe(200);const list=await res.json();expect(Array.isArray(list)).toBe(true);expect(list.length).toBe(2);});
