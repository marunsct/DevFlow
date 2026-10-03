// Reference implementation of the fullstack-bookmarks benchmark (no dependencies).
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const dataDir = process.env.DATA_DIR || 'data';
const file = path.join(dataDir, 'bookmarks.json');
const load = () => (fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : { next: 1, items: [] });
const store = (db) => { fs.mkdirSync(dataDir, { recursive: true }); fs.writeFileSync(file, JSON.stringify(db)); };
const send = (res, code, body) => {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(body === undefined ? '' : JSON.stringify(body));
};

http.createServer((req, res) => {
  if (req.url === '/' || req.url === '/index.html' || req.url === '/app.js') {
    const name = req.url === '/app.js' ? 'app.js' : 'index.html';
    res.writeHead(200, { 'Content-Type': name.endsWith('.js') ? 'text/javascript' : 'text/html' });
    return res.end(fs.readFileSync(path.join(__dirname, 'public', name)));
  }
  if (req.url === '/api/bookmarks' && req.method === 'GET') return send(res, 200, [...load().items].reverse());
  if (req.url === '/api/bookmarks' && req.method === 'POST') {
    let raw = '';
    req.on('data', (c) => { raw += c; });
    return req.on('end', () => {
      let b = {};
      try { b = JSON.parse(raw || '{}'); } catch { b = {}; }
      if (!String(b.title || '').trim() || !/^https?:\/\//.test(String(b.url || ''))) return send(res, 422, { error: 'invalid' });
      const db = load();
      const item = { id: db.next++, title: b.title.trim(), url: b.url, tag: String(b.tag || '').trim() };
      db.items.push(item); store(db); send(res, 201, item);
    });
  }
  const match = req.url.match(/^\/api\/bookmarks\/(\d+)$/);
  if (match && req.method === 'DELETE') {
    const db = load();
    const kept = db.items.filter((i) => i.id !== Number(match[1]));
    if (kept.length === db.items.length) return send(res, 404, { error: 'not found' });
    db.items = kept; store(db); return send(res, 204);
  }
  send(res, 404, { error: 'not found' });
}).listen(Number(process.env.PORT || 3000), '127.0.0.1');
