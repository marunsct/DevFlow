import { Router } from 'express';
import { validateBookmark } from '../validators/bookmark.js';
import * as data from '../data/bookmarks.js';

const router = Router();

// GET /api/bookmarks — returns bookmark list as JSON (newest-first order).
// This route is mounted under /api/bookmarks, so all requests to it should
// return JSON. The HTML page for the browser is served separately by express.static()
// at the root path (/) via app.js middleware ordering.
router.get('/', async (request, response) => {
  const bookmarks = data.loadBookmarks();
  // Spread into a copy so we don't mutate the in-memory array.
  const sortedBookmarks = [...bookmarks].sort((a, b) => b.created_at - a.created_at);
  return response.status(200).json(sortedBookmarks);
});

// POST /api/bookmarks — creates a new bookmark.
router.post('/', async (request, response) => {
  // Guard against missing or non-object body to prevent TypeError from destructuring undefined.
  // When no body is sent (or Content-Type is not application/json), express.json() does not
  // populate request.body, leaving it undefined. Without this guard the route crashes with 500.
  if (!request.body || typeof request.body !== 'object') {
    return response.status(400).json({ error: 'Request body is required' });
  }

  const { title, url, tag } = request.body;

  // Validate input using the validator module
  const validation = validateBookmark({ title, url, tag });

  if (!validation.valid) {
    return response.status(validation.error.status).json({ error: validation.error.message });
  }

  try {
    // Create bookmark via data layer
    const newBookmark = data.createBookmark({ title, url, tag });
    response.status(201).json(newBookmark);
  } catch (error) {
    // In case of unexpected errors during creation/persistence
    console.error('Error creating bookmark:', error);
    response.status(500).json({ error: 'Internal server error' });
  }
});

// DELETE /api/bookmarks/:id — deletes a bookmark by ID.
router.delete('/:id', async (request, response) => {
  const id = request.params.id;

  // Security: Reject paths containing '..' or '/' in the id segment
  if (id.includes('..') || id.includes('/')) {
    return response.status(400).json({ error: 'Invalid bookmark ID' });
  }

  try {
    const result = data.deleteBookmark(id);

    if (result.deleted) {
      response.status(204).send();
    } else {
      response.status(404).json({ error: 'Bookmark not found' });
    }
  } catch (error) {
    console.error('Error deleting bookmark:', error);
    response.status(500).json({ error: 'Internal server error' });
  }
});

export { router };
