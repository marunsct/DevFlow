import { test, expect } from '@playwright/test';
import { startService } from './service.cjs';

// AC-6: Notes survive a restart of the service
// AC-17: Notes persist across restarts
// Uses the harness helper to stop and restart the service on the same DATA_DIR.
test('[AC-6][AC-17] notes survive a service restart', async ({ request }) => {
  // Start the service on a random port with a fresh DATA_DIR
  const first = await startService();

  // Create two notes via the first service instance
  const create1 = await request.post(first.baseURL + '/notes', {
    data: { title: 'Persist note 1', body: 'Body 1' },
  });
  expect(create1.status()).toBe(201);
  const note1 = await create1.json();
  expect(note1.title).toBe('Persist note 1');
  expect(typeof note1.id).toBe('number');

  const create2 = await request.post(first.baseURL + '/notes', {
    data: { title: 'Persist note 2', body: 'Body 2' },
  });
  expect(create2.status()).toBe(201);
  const note2 = await create2.json();
  expect(note2.title).toBe('Persist note 2');

  // Verify both notes exist before stopping
  const list1 = await request.get(first.baseURL + '/notes');
  expect(list1.status()).toBe(200);
  const notes1 = await list1.json();
  expect(Array.isArray(notes1)).toBeTruthy();
  expect(notes1.length).toBe(2);

  // Stop the service
  await first.stop();

  // Restart with the same DATA_DIR on a new random port
  const second = await startService({ dataDir: first.dataDir });

  // Verify notes survived the restart
  const list2 = await request.get(second.baseURL + '/notes');
  expect(list2.status()).toBe(200);
  const notes2 = await list2.json();
  expect(Array.isArray(notes2)).toBeTruthy();
  expect(notes2.length).toBe(2);

  // Verify the specific notes we created are still there
  const ids = notes2.map((n) => n.id).sort((a, b) => a - b);
  const expectedIds = [note1.id, note2.id].sort((a, b) => a - b);
  expect(ids).toEqual(expectedIds);

  // Verify we can still create new notes after restart
  const create3 = await request.post(second.baseURL + '/notes', {
    data: { title: 'Post-restart note', body: 'Body 3' },
  });
  expect(create3.status()).toBe(201);
  const note3 = await create3.json();
  expect(note3.title).toBe('Post-restart note');

  // Verify all three notes exist
  const list3 = await request.get(second.baseURL + '/notes');
  expect(list3.status()).toBe(200);
  const notes3 = await list3.json();
  expect(Array.isArray(notes3)).toBeTruthy();
  expect(notes3.length).toBe(3);

  await second.stop();
});
