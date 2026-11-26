import { Hono } from 'hono';
import type { Context } from 'hono';
import * as store from './store.ts';
import type { Store } from './store.ts';
import { validateNoteBody } from './validation.ts';

let currentStore: Store | null = null;

export function defineRoutes(app: Hono, storeInstance: Store): void {
  currentStore = storeInstance;

  // GET /health
  app.get('/health', healthCheckHandler);

  // POST /notes
  app.post('/notes', createNoteHandler);

  // GET /notes
  app.get('/notes', listNotesHandler);

  // GET /notes/:id
  app.get('/notes/:id', getNoteHandler);

  // PUT /notes/:id
  app.put('/notes/:id', updateNoteHandler);

  // DELETE /notes/:id
  app.delete('/notes/:id', deleteNoteHandler);
}

async function createNoteHandler(c: Context): Promise<Response> {
  try {
    let body: unknown;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: 'Invalid request body' }, 400);
    }

    const result = validateNoteBody(body);

    if (!result.valid) {
      // Validation failed — return 400 with the error message (per ADR-07)
      return c.json({ error: result.error! }, 400);
    }

    if (!currentStore) {
      throw new Error('Store not initialized');
    }

    const note = store.createNote(currentStore, result.data!.title, result.data!.body);
    return c.json(note, 201);
  } catch (err) {
    console.error(err);
    return c.json({ error: 'Internal server error' }, 500);
  }
}

async function listNotesHandler(c: Context): Promise<Response> {
  try {
    if (!currentStore) {
      throw new Error('Store not initialized');
    }

    const notes = store.getAllNotes(currentStore);
    return c.json(notes, 200);
  } catch (err) {
    console.error(err);
    return c.json({ error: 'Internal server error' }, 500);
  }
}

async function getNoteHandler(c: Context): Promise<Response> {
  try {
    if (!currentStore) {
      throw new Error('Store not initialized');
    }

    const idParam = c.req.param('id');
    // Handle potential undefined if param is missing, though route pattern usually ensures presence
    if (idParam === undefined) {
        return c.json({ error: 'Invalid ID' }, 400);
    }
    
    const id = parseInt(idParam, 10);
    
    if (isNaN(id)) {
      return c.json({ error: 'Invalid ID' }, 400);
    }

    const note = store.getNoteById(currentStore, id);
    return c.json(note, 200);
  } catch (err) {
    if (err instanceof Error && err.message === 'Not Found') {
      return c.body('', 404);
    }
    console.error(err);
    return c.json({ error: 'Internal server error' }, 500);
  }
}

async function updateNoteHandler(c: Context): Promise<Response> {
  try {
    if (!currentStore) {
      throw new Error('Store not initialized');
    }

    const idParam = c.req.param('id');
    // Handle potential undefined if param is missing
    if (idParam === undefined) {
        return c.json({ error: 'Invalid ID' }, 400);
    }

    const id = parseInt(idParam, 10);
    
    if (isNaN(id)) {
      return c.json({ error: 'Invalid ID' }, 400);
    }

    let body: unknown;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: 'Invalid request body' }, 400);
    }

    const result = validateNoteBody(body);

    if (!result.valid) {
      // Validation failed — return 400 with the error message (per ADR-07)
      return c.json({ error: result.error! }, 400);
    }

    try {
      const note = store.updateNote(currentStore, id, result.data!.title, result.data!.body);
      return c.json(note, 200);
    } catch (err) {
      if (err instanceof Error && err.message === 'Not Found') {
        return c.body('', 404);
      }
      throw err;
    }
  } catch (err) {
    console.error(err);
    return c.json({ error: 'Internal server error' }, 500);
  }
}

async function deleteNoteHandler(c: Context): Promise<Response> {
  try {
    if (!currentStore) {
      throw new Error('Store not initialized');
    }

    const idParam = c.req.param('id');
    // Handle potential undefined if param is missing
    if (idParam === undefined) {
        return c.json({ error: 'Invalid ID' }, 400);
    }

    const id = parseInt(idParam, 10);
    
    if (isNaN(id)) {
      return c.json({ error: 'Invalid ID' }, 400);
    }

    try {
      store.deleteNote(currentStore, id);
      return c.body(null, 204);
    } catch (err) {
      if (err instanceof Error && err.message === 'Not Found') {
        return c.body('', 404);
      }
      throw err;
    }
  } catch (err) {
    console.error(err);
    return c.json({ error: 'Internal server error' }, 500);
  }
}

function healthCheckHandler(c: Context): Response {
  return c.json({}, 200);
}
