// Pure task logic - the single place task rules live.
// No DOM, no storage, no imports; every function takes plain arguments
// and returns a new array/task without mutating its input.

export function createTask(title, description = '') {
  return {
    id: crypto.randomUUID(),
    title: String(title).trim(),
    description: typeof description === 'string' ? description : '',
    completed: false,
  };
}

export function addTask(tasks, task) {
  if (tasks.some((t) => t.id === task.id)) {
    return tasks.slice();
  }
  return [...tasks, { ...task }];
}

export function toggleTask(tasks, id) {
  if (!tasks.some((t) => t.id === id)) {
    return tasks.slice();
  }
  return tasks.map((t) => (t.id === id ? { ...t, completed: !t.completed } : t));
}

export function updateTitle(tasks, id, newTitle) {
  const trimmed = String(newTitle).trim();
  if (!trimmed || !tasks.some((t) => t.id === id)) {
    return tasks.slice();
  }
  return tasks.map((t) => (t.id === id ? { ...t, title: trimmed } : t));
}

export function deleteTask(tasks, id) {
  if (!tasks.some((t) => t.id === id)) {
    return tasks.slice();
  }
  return tasks.filter((t) => t.id !== id);
}

export function filterTasks(tasks, filter) {
  if (filter === 'active') {
    return tasks.filter((t) => t.completed === false);
  }
  if (filter === 'completed') {
    return tasks.filter((t) => t.completed === true);
  }
  return tasks.slice();
}
