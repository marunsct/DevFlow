// Reference for the notes-api-js benchmark: Node's own http module, a JSON file
// under DATA_DIR. It proves the hidden tests (shared with notes-api) are right.
import { createServer } from 'node:http';
import { mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';

const dataDir = process.env.DATA_DIR || '.';
const file = join(dataDir, 'notes.json');
mkdirSync(dataDir, { recursive: true });

function load() {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return { next: 1, notes: [] };
  }
}

function save(store) {
  writeFileSync(`${file}.tmp`, JSON.stringify(store));
  renameSync(`${file}.tmp`, file);
}

function send(res, status, body) {
  if (body === undefined) {
    res.writeHead(status).end();
    return;
  }
  res.writeHead(status, { 'content-type': 'application/json' }).end(JSON.stringify(body));
}

function valid(body) {
  return body && typeof body.title === 'string' && body.title.trim() !== '';
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (chunk) => { raw += chunk; });
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : null);
      } catch {
        resolve(null);
      }
    });
  });
}

const server = createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  if (path === '/health' && req.method === 'GET') return send(res, 200, { status: 'ok' });

  const store = load();
  if (path === '/notes') {
    if (req.method === 'GET') return send(res, 200, store.notes);
    if (req.method === 'POST') {
      const body = await readBody(req);
      if (!valid(body)) return send(res, 422, { error: 'title is required' });
      const note = { id: store.next, title: body.title, body: typeof body.body === 'string' ? body.body : '' };
      store.next += 1;
      store.notes.push(note);
      save(store);
      return send(res, 201, note);
    }
    return send(res, 405, { error: 'method not allowed' });
  }

  const match = path.match(/^\/notes\/(\d+)$/);
  if (!match) return send(res, 404, { error: 'not found' });
  const index = store.notes.findIndex((n) => n.id === Number(match[1]));
  if (req.method === 'GET') return index < 0 ? send(res, 404, { error: 'not found' }) : send(res, 200, store.notes[index]);
  if (req.method === 'PUT') {
    const body = await readBody(req);
    if (index < 0) return send(res, 404, { error: 'not found' });
    if (!valid(body)) return send(res, 422, { error: 'title is required' });
    store.notes[index] = { ...store.notes[index], title: body.title, body: typeof body.body === 'string' ? body.body : '' };
    save(store);
    return send(res, 200, store.notes[index]);
  }
  if (req.method === 'DELETE') {
    if (index < 0) return send(res, 404, { error: 'not found' });
    store.notes.splice(index, 1);
    save(store);
    return send(res, 204);
  }
  return send(res, 405, { error: 'method not allowed' });
});

server.listen(Number(process.env.PORT || 3000), '127.0.0.1');
