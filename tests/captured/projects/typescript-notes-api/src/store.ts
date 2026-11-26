import { readFileSync, writeFileSync, renameSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

export interface Note {
  id: number;
  title: string;
  body: string;
}

export interface Store {
  notes: Note[];
  nextId: number;
}

let currentDataDir: string | null = null;

export function loadStore(dataDir?: string): Store {
  const dir = dataDir || process.env.DATA_DIR || 'data';
  currentDataDir = dir;

  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  const filePath = join(dir, 'notes.json');

  try {
    const content = readFileSync(filePath, 'utf-8');
    if (!content.trim()) {
      const initialStore: Store = { notes: [], nextId: 1 };
      saveStore(initialStore);
      return initialStore;
    }

    const parsed = JSON.parse(content);

    if (!Array.isArray(parsed.notes)) {
      throw new Error('Invalid store format');
    }

    const store: Store = {
      notes: parsed.notes,
      nextId: parsed.nextId || (parsed.notes.length > 0 ? Math.max(...parsed.notes.map((n: Note) => n.id), 0) + 1 : 1)
    };

    return store;
  } catch (err: any) {
    if (err.code === 'ENOENT') {
      const initialStore: Store = { notes: [], nextId: 1 };
      saveStore(initialStore);
      return initialStore;
    }
    throw new Error('Failed to load store');
  }
}

export function saveStore(store: Store): void {
  if (!currentDataDir) {
    throw new Error('Store not initialized with dataDir');
  }

  const filePath = join(currentDataDir, 'notes.json');
  const tmpPath = join(currentDataDir, 'notes.json.tmp');

  const content = JSON.stringify({
    notes: store.notes,
    nextId: store.nextId
  }, null, 2);

  writeFileSync(tmpPath, content, 'utf-8');
  renameSync(tmpPath, filePath);
}

export function getAllNotes(store: Store): Note[] {
  return [...store.notes];
}

export function getNoteById(store: Store, id: number): Note {
  const note = store.notes.find(n => n.id === id);
  if (!note) {
    throw new Error('Not Found');
  }
  return { ...note };
}

export function createNote(store: Store, title: string, body: string): Note {
  const nextId = Math.max(...store.notes.map(n => n.id), 0) + 1;

  const newNote: Note = {
    id: nextId,
    title,
    body
  };

  store.notes.push(newNote);
  store.nextId = nextId + 1;

  saveStore(store);

  return { ...newNote };
}

export function updateNote(store: Store, id: number, title: string, body: string): Note {
  const noteIndex = store.notes.findIndex(n => n.id === id);

  if (noteIndex === -1) {
    throw new Error('Not Found');
  }

  store.notes[noteIndex].title = title;
  store.notes[noteIndex].body = body;

  saveStore(store);

  return { ...store.notes[noteIndex] };
}

export function deleteNote(store: Store, id: number): void {
  const noteIndex = store.notes.findIndex(n => n.id === id);

  if (noteIndex === -1) {
    throw new Error('Not Found');
  }

  store.notes.splice(noteIndex, 1);

  saveStore(store);
}
