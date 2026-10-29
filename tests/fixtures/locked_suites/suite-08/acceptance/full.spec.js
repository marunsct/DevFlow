import { test, expect } from '@playwright/test';

async function createNote(request,payload){const res=await request.post('/notes',{data:payload});expect(res.status()).toBe(201);return await res.json();}

test('[AC-1][AC-8] POST /notes creates a note and returns 201 with the note', async ({request})=>{const payload={title:'Test Note',body:'Body content'};const res=await request.post('/notes',{data:payload});expect(res.status()).toBe(201);const json=await res.json();expect(json).toMatchObject(payload);expect(typeof json.id).toBe('number');});

test('[AC-2][AC-9] GET /notes returns all created notes', async ({request})=>{const p1={title:'Note One',body:'First'};const p2={title:'Note Two',body:'Second'};await createNote(request,p1);await createNote(request,p2);const res=await request.get('/notes');expect(res.status()).toBe(200);const list=await res.json();expect(Array.isArray(list)).toBe(true);const titles=list.map(n=>n.title);expect(titles).toContain(p1.title);expect(titles).toContain(p2.title);});

test('[AC-3][AC-10] GET /notes/:id returns the note or 404', async ({request})=>{const payload={title:'Fetch Me',body:''};const created=await createNote(request,payload);let res=await request.get(`/notes/${created.id}`);expect(res.status()).toBe(200);const fetched=await res.json();expect(fetched).toEqual(created);res=await request.get('/notes/9999999');expect(res.status()).toBe(404);const err=await res.json();expect(err).toEqual({error:'Not found'});});

test('[AC-4] PUT /notes/:id updates a note', async ({request})=>{const payload={title:'Old Title',body:'Old Body'};const created=await createNote(request,payload);const upd={title:'New Title',body:'Updated Body'};let res=await request.put(`/notes/${created.id}`,{data:upd});expect(res.status()).toBe(200);const updated=await res.json();expect(updated).toEqual({id:created.id,...upd});res=await request.get(`/notes/${created.id}`);const fetched=await res.json();expect(fetched).toEqual(updated);});

test('[AC-5][AC-12] DELETE /notes/:id removes a note', async ({request})=>{const payload={title:'Delete Me',body:''};const created=await createNote(request,payload);let res=await request.delete(`/notes/${created.id}`);expect(res.status()).toBe(204);res=await request.get(`/notes/${created.id}`);expect(res.status()).toBe(404);});

test('[AC-7] Note objects have correct property types', async ({request})=>{const payload={title:'Typed Note',body:'Check Types'};await createNote(request,payload);const res=await request.get('/notes');expect(res.status()).toBe(200);const list=await res.json();list.forEach(note=>{expect(typeof note.id).toBe('number');expect(typeof note.title).toBe('string');expect(typeof note.body).toBe('string');});});

test('[AC-13][AC-18] POST without title returns 400 and does not persist', async ({request})=>{const res=await request.post('/notes',{data:{body:'No title'}});expect(res.status()).toBe(400);const err=await res.json();expect(err).toEqual({error:'Title required'});const listRes=await request.get('/notes');const list=await listRes.json();const titles=list.map(n=>n.title);expect(titles).not.toContain('');});

test('[AC-16] Create, read, update, delete sequence works', async ({request})=>{const payload={title:'Sequence Note',body:'Start'};const created=await createNote(request,payload);let res=await request.get(`/notes/${created.id}`);expect(res.status()).toBe(200);let fetched=await res.json();expect(fetched).toEqual(created);const upd={title:'Updated Seq',body:'Middle'};res=await request.put(`/notes/${created.id}`,{data:upd});expect(res.status()).toBe(200);const updated=await res.json();expect(updated).toEqual({id:created.id,...upd});res=await request.delete(`/notes/${created.id}`);expect(res.status()).toBe(204);});
