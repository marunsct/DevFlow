import { test, expect } from '@playwright/test';

async function postNote(request, title, body) {
  const res = await request.post('/notes', { data: { title, body } });
  return res;
}

test('[AC-13][AC-18] POST /notes without title returns 400 and no note stored', async ({ request }) => {
  const res = await postNote(request, '', 'Body');
  expect(res.status()).toBe(400);
});
