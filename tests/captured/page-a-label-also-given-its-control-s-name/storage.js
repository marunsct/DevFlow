// LocalStorage persistence adapter.
// No DOM, no storage globals - the store argument is the only storage handle,
// so the same code works against window.localStorage in the page and a plain
// object in tests.

export const TASKS_STORAGE_KEY = 'simple-to-do-list.tasks';

export function loadTasks(store) {
  try {
    const raw = store.getItem(TASKS_STORAGE_KEY);
    if (raw === null || raw === undefined) {
      return [];
    }
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) {
      return [];
    }
    const tasks = [];
    for (const entry of data) {
      if (entry === null || typeof entry !== 'object') {
        continue;
      }
      if (typeof entry.id !== 'string' || entry.id === '') {
        continue;
      }
      if (typeof entry.title !== 'string' || entry.title.trim() === '') {
        continue;
      }
      if (typeof entry.completed !== 'boolean') {
        continue;
      }
      tasks.push({
        id: entry.id,
        title: entry.title,
        description: typeof entry.description === 'string' ? entry.description : '',
        completed: entry.completed === true,
      });
    }
    return tasks;
  } catch {
    return [];
  }
}

export function saveTasks(store, tasks) {
  const value = JSON.stringify(tasks);
  store.setItem(TASKS_STORAGE_KEY, value);
}
