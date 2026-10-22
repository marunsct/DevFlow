import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

type Note = { id: number; title: string; body: string };

const dataDir = process.env.DATA_DIR ?? 'data';
const file = path.join(dataDir, 'notes.json');
mkdirSync(dataDir, { recursive: true });

function load(): Note[] {
  try {
    return JSON.parse(readFileSync(file, 'utf8')) as Note[];
  } catch {
    return [];
  }
}

function save(notes: Note[]): void {
  writeFileSync(file, JSON.stringify(notes));
}

function valid(input: unknown): { title: string; body: string } | null {
  if (!input || typeof input !== 'object') return null;
  const { title, body } = input as Record<string, unknown>;
  if (typeof title !== 'string' || title.trim() === '') return null;
  return { title, body: typeof body === 'string' ? body : '' };
}

const app = new Hono();

app.get('/health', (c) => c.json({ status: 'ok' }));
app.get('/notes', (c) => c.json(load()));
app.get('/notes/:id', (c) => {
  const note = load().find((n) => n.id === Number(c.req.param('id')));
  return note ? c.json(note) : c.json({ error: 'not found' }, 404);
});
app.post('/notes', async (c) => {
  const input = valid(await c.req.json().catch(() => null));
  if (!input) return c.json({ error: 'a title is required' }, 400);
  const notes = load();
  const note = { id: notes.reduce((max, n) => Math.max(max, n.id), 0) + 1, ...input };
  save([...notes, note]);
  return c.json(note, 201);
});
app.put('/notes/:id', async (c) => {
  const input = valid(await c.req.json().catch(() => null));
  if (!input) return c.json({ error: 'a title is required' }, 400);
  const notes = load();
  const note = notes.find((n) => n.id === Number(c.req.param('id')));
  if (!note) return c.json({ error: 'not found' }, 404);
  Object.assign(note, input);
  save(notes);
  return c.json(note);
});
app.delete('/notes/:id', (c) => {
  const notes = load();
  const kept = notes.filter((n) => n.id !== Number(c.req.param('id')));
  if (kept.length === notes.length) return c.json({ error: 'not found' }, 404);
  save(kept);
  return c.body(null, 204);
});

serve({ fetch: app.fetch, port: Number(process.env.PORT ?? 3000), hostname: '127.0.0.1' });
