// Storage adapter: reads and writes the task list through a Storage-like object
// (getItem and setItem only), so tests can pass a plain object.
import { parseTasks, serialiseTasks } from './tasks.js';

export const TASKS_KEY = 'todo.tasks';
export const VERSION_KEY = 'todo.version';
export const SCHEMA_VERSION = '1';

// Reads the stored task list. If the storage read throws, returns an empty list.
// Never writes, so a bad stored value is kept until the next successful save.
export function loadTasks(storage) {
  let raw;
  try {
    raw = storage.getItem(TASKS_KEY);
  } catch (error) {
    return [];
  }
  return parseTasks(raw);
}

// Writes the tasks first, then the schema version. Returns {ok, message}
// instead of throwing; the message is shown to the user on failure.
export function saveTasks(storage, tasks) {
  try {
    storage.setItem(TASKS_KEY, serialiseTasks(tasks));
    storage.setItem(VERSION_KEY, SCHEMA_VERSION);
    return { ok: true, message: null };
  } catch (error) {
    if (error && (error.name === 'QuotaExceededError' || error.code === 22 || error.code === 1014)) {
      return { ok: false, message: 'Storage is full. The change was not saved.' };
    }
    return { ok: false, message: 'Tasks cannot be saved in this browser.' };
  }
}
