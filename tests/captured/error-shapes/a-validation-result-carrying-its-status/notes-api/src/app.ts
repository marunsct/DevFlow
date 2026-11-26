import { Hono } from 'hono';
import type { Context } from 'hono';
import { createStore } from './store.ts';
import { parseNoteBody, parseId } from './validation.ts';

// Builds the service. `src/main.ts` serves it; unit tests call `app.request(...)` on it directly.
export function createApp(dataDir?: string): Hono {
  const store = createStore(dataDir);
  const app = new Hono();

  app.get('/health', (c) => c.json({ status: 'ok' }));

  app.post('/notes', async (c) => {
    const raw = await c.req.text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return c.json({ error: 'invalid JSON body' }, 400);
    }
    const validation = parseNoteBody(parsed);
    if (!validation.ok) {
      return c.json({ error: validation.error }, validation.status);
    }
    const note = store.create(validation.title, validation.body);
    return c.json(note, 201);
  });

  app.get('/notes', (c) => {
    return c.json(store.list());
  });

  app.get('/notes/:id', (c) => {
    const id = parseId(c.req.param('id'));
    if (id === null) {
      return c.json({ error: 'note not found' }, 404);
    }
    const note = store.get(id);
    if (!note) {
      return c.json({ error: 'note not found' }, 404);
    }
    return c.json(note);
  });

  // An empty id segment is not a positive integer, so it is not found either — no store access.
  app.get('/notes/', (c) => {
    return c.json({ error: 'note not found' }, 404);
  });

  app.put('/notes/:id', async (c) => {
    const raw = await c.req.text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return c.json({ error: 'invalid JSON body' }, 400);
    }
    const validation = parseNoteBody(parsed);
    if (!validation.ok) {
      return c.json({ error: validation.error }, validation.status);
    }
    const id = parseId(c.req.param('id'));
    if (id === null) {
      return c.json({ error: 'note not found' }, 404);
    }
    const note = store.replace(id, validation.title, validation.body);
    if (!note) {
      return c.json({ error: 'note not found' }, 404);
    }
    return c.json(note);
  });

  app.delete('/notes/:id', (c) => {
    const id = parseId(c.req.param('id'));
    if (id === null) {
      return c.json({ error: 'note not found' }, 404);
    }
    if (!store.delete(id)) {
      return c.json({ error: 'note not found' }, 404);
    }
    return c.body(null, 204);
  });

  app.notFound((c) => c.json({ error: 'not found' }, 404));

  app.onError((err: Error, c: Context) => {
    return c.json({ error: 'internal server error' }, 500);
  });

  return app;
}
