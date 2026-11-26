import type { Task } from './types';

/**
 * Reads tasks from localStorage.
 * 
 * @returns An array of Task objects. Returns an empty array if the key is missing or parsing fails.
 */
export function readTasks(): Task[] {
  try {
    const stored = localStorage.getItem('todo-tasks');
    if (!stored) {
      return [];
    }
    const parsed = JSON.parse(stored);
    if (parsed && Array.isArray(parsed.tasks)) {
      return parsed.tasks;
    }
    return [];
  } catch (e) {
    // In case of SecurityError, TypeError, or JSON parse error
    return [];
  }
}

/**
 * Saves tasks to localStorage.
 * 
 * @param tasks - The array of Task objects to persist.
 */
export function saveTasks(tasks: Task[]): void {
  try {
    localStorage.setItem('todo-tasks', JSON.stringify({ tasks }));
  } catch (e) {
    // In case of SecurityError or other storage errors, silently fail as per spec requirements
    // "No specific user-facing message is implemented"
  }
}
