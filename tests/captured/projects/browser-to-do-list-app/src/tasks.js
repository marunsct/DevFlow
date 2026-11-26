// Pure task logic: no DOM, no localStorage, no imports.
// Every mutating function returns a new array and never changes its input.

export const EMPTY_TITLE_MESSAGE = 'Enter a title to add the task.';
export const FILTERS = ['all', 'active', 'completed'];

// A title is valid when it is a string whose trimmed length is at least 1.
function isValidTitle(title) {
  return typeof title === 'string' && title.trim().length >= 1;
}

// Returns a unique id. Uses crypto.randomUUID when the browser has it; otherwise
// increments counterRef.value and combines it with the time (fallback only).
export function generateId(counterRef) {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  counterRef.value += 1;
  return `${Date.now().toString(36)}-${counterRef.value}`;
}

// Adds a task at the end of the list. Returns {tasks, error}; on error the
// original array reference is returned unchanged.
export function create(tasks, title, description, newId) {
  if (!isValidTitle(title)) {
    return { tasks, error: EMPTY_TITLE_MESSAGE };
  }
  return {
    tasks: [
      ...tasks,
      {
        id: newId,
        title: title.trim(),
        description: typeof description === 'string' ? description : '',
        completed: false,
      },
    ],
    error: null,
  };
}

// Replaces title and description of the task with the given id, keeping its
// id, position and completed flag. Unknown id: list unchanged, no error.
export function edit(tasks, id, title, description) {
  if (!isValidTitle(title)) {
    return { tasks, error: EMPTY_TITLE_MESSAGE };
  }
  if (!tasks.some((entry) => entry.id === id)) {
    return { tasks, error: null };
  }
  return {
    tasks: tasks.map((entry) => (entry.id === id
      ? {
        id: entry.id,
        title: title.trim(),
        description: typeof description === 'string' ? description : '',
        completed: entry.completed,
      }
      : entry)),
    error: null,
  };
}

// Returns a new array with the matching task's completed flag inverted.
// Other entries are the same objects.
export function toggle(tasks, id) {
  return tasks.map((entry) => (entry.id === id
    ? { ...entry, completed: !entry.completed }
    : entry));
}

// Returns a new array without the task whose id matches.
export function remove(tasks, id) {
  return tasks.filter((entry) => entry.id !== id);
}

// 'active' keeps incomplete tasks, 'completed' keeps completed tasks; any other
// value returns all tasks. Stored order is kept.
export function filterTasks(tasks, filter) {
  if (filter === 'active') return tasks.filter((entry) => entry.completed === false);
  if (filter === 'completed') return tasks.filter((entry) => entry.completed === true);
  return tasks.slice();
}

// Turns stored text into a clean task list. Invalid JSON, a non-array, or
// invalid entries yield fewer tasks instead of an error. Entries missing a
// usable id or title are dropped, and a repeated id keeps only its first copy.
export function parseTasks(raw) {
  if (typeof raw !== 'string') return [];
  let data;
  try {
    data = JSON.parse(raw);
  } catch (error) {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const kept = [];
  const seen = new Set();
  for (const entry of data) {
    if (entry === null || typeof entry !== 'object') continue;
    if (typeof entry.id !== 'string' || entry.id.length === 0) continue;
    if (typeof entry.title !== 'string' || entry.title.trim().length === 0) continue;
    if (seen.has(entry.id)) continue;
    seen.add(entry.id);
    kept.push({
      id: entry.id,
      title: entry.title,
      description: typeof entry.description === 'string' ? entry.description : '',
      completed: entry.completed === true,
    });
  }
  return kept;
}

// Produces the JSON text stored under the tasks key; only the four task fields
// are written.
export function serialiseTasks(tasks) {
  return JSON.stringify(tasks.map((t) => ({
    id: t.id,
    title: t.title,
    description: t.description,
    completed: t.completed,
  })));
}
