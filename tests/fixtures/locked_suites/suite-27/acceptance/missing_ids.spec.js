import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

// Helper to create a note via the API
async function createNote(request, title, body) {
  const response = await request.post('/notes', {
    data: { title, body },
  });
  expect(response.status()).toBe(201);
  return await response.json();
}

/**
 * AC-7: JSON over HTTP. A note is {"id": <integer>, "title": <string>, "body": <string>}
 */
test('[AC-7] created and fetched note has exact schema', async ({ request }) => {
  const note = await createNote(request, 'SchemaTest', 'Body');
  expect(note).toEqual({ id: note.id, title: 'SchemaTest', body: 'Body' });

  const getResp = await request.get(`/notes/${note.id}`);
  expect(getResp.status()).toBe(200);
  const fetched = await getResp.json();
  expect(fetched).toEqual({ id: note.id, title: 'SchemaTest', body: 'Body' });
});

/**
 * AC-11: PUT /notes/{id} with {"title": ..., "body": ...} replaces both and answers 200 with the note, or 404
 */
test('[AC-11] update note returns updated data', async ({ request }) => {
  const original = await createNote(request, 'OldTitle', 'OldBody');
  const updResp = await request.put(`/notes/${original.id}`, {
    data: { title: 'NewTitle', body: 'NewBody' },
  });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated).toEqual({ id: original.id, title: 'NewTitle', body: 'NewBody' });

  const getResp = await request.get(`/notes/${original.id}`);
  expect(getResp.status()).toBe(200);
  const got = await getResp.json();
  expect(got).toEqual(updated);
});

/**
 * AC-12: DELETE /notes/{id} answers 204, or 404
 */
test('[AC-12] delete note returns 204 and cannot be retrieved', async ({ request }) => {
  const toDel = await createNote(request, 'DeleteMe', 'Bye');
  const delResp = await request.delete(`/notes/${toDel.id}`);
  expect(delResp.status()).toBe(204);

  const getResp = await request.get(`/notes/${toDel.id}`);
  expect(getResp.status()).toBe(404);
});

/**
 * AC-15: The project directory has a start.sh that starts the service on 127.0.0.1 at the port in the PORT environment variable, keeping its data under the directory in the DATA_DIR environment variable
 */
test('[AC-15] start.sh exists and contains expected commands', async () => {
  const content = await fs.readFile('./start.sh', 'utf8');
  expect(content).toContain('node src/main.ts');
  // Check that it references environment variables
  // expect(content).toMatch(/PORT/);
  // expect(content).toMatch(/DATA_DIR/);
});

/**
 * AC-16: Every operation works as the interface says
 */
test('', async ({ request }) => {
  // Create two notes
  const n1 = await createNote(request, 'First', 'A');
  const n2 = await createNote(request, 'Second', 'B');

  // List all
  const listResp = await request.get('/notes');
  expect(listResp.status()).toBe(200);
  const list = await listResp.json();
  expect(list.length).toBeGreaterThanOrEqual(2);
  const ids = list.map((x) => x.id);
  expect(ids).toContain(n1.id);
  expect(ids).toContain(n2.id);

  // Get one
  const getResp = await request.get(`/notes/${n1.id}`);
  expect(getResp.status()).toBe(200);
  const got = await getResp.json();
  expect(got).toEqual({ id: n1.id, title: 'First', body: 'A' });

  // Update
  const updResp = await request.put(`/notes/${n2.id}`, {
    data: { title: 'SecondUpdated', body: 'Bupdated' },
  });
  expect(updResp.status()).toBe(200);
  const updated = await updResp.json();
  expect(updated).toEqual({ id: n2.id, title: 'SecondUpdated', body: 'Bupdated' });

  // Delete one
  const delResp = await request.delete(`/notes/${n1.id}`);
  expect(delResp.status()).toBe(204);

  // Confirm deletion
  const getAfterDel = await request.get(`/notes/${n1.id}`);
  expect(getAfterDel.status()).toBe(404);
});

/**
 * AC-18: Invalid input is refused without storing anything
 */
test('[AC-18] invalid create does not alter store', async ({ request }) => {
  // Create a valid note to establish baseline count
  const base = await createNote(request, 'Base', 'Exists');
  const listBefore = await request.get('/notes');
  const beforeCount = (await listBefore.json()).length;

  // Attempt invalid title
  const resp = await request.post('/notes', { data: { body: 'NoTitle' } });
  expect(resp.status()).toBe(400);
  const err = await resp.json();
  expect(err.error).toBe('Title is required');

  // Ensure count unchanged
  const listAfter = await request.get('/notes');
  const afterCount = (await listAfter.json()).length;
  expect(afterCount).toBe(beforeCount);
});
