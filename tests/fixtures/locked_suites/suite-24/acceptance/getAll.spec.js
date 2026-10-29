import { test, expect } from '@playwright/test';

// Helper to create a note via POST /notes
async function createNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  expect(res.status()).toBe(201);
  const json = await res.json();
  expect(json).toHaveProperty('id');
  return json.id;
}

// Helper to delete a note
async function deleteNote(request, id) {
  const res = await request.delete(`/notes/${id}`);
  expect(res.status()).toBe(204);
}

test('[AC-9] GET /notes returns array of all notes', async ({ request }) => {
  // create two notes
  const id1 = await createNote(request, 'A', 'B');
  const id2 = await createNote(request, 'C', 'D');
  // get list
  const res = await request.get('/notes');
  expect(res.status()).toBe(200);
  const list = await res.json();
  expect(Array.isArray(list)).toBeTruthy();
  expect(list.length).toBe(2);
  // verify presence by id
  const ids = list.map((n) => n.id);
  expect(ids).toContain(id1);
  expect(ids).toContain(id2);
  // cleanup
  await deleteNote(request, id1);
  await deleteNote(request, id2);
});
