import { describe, it, expect, beforeEach } from 'vitest';
import { readTasks, saveTasks } from '../src/storage';
import type { Task } from '../src/types';

describe('storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('readTasks', () => {
    it('returns an empty array when the key is missing', () => {
      const tasks = readTasks();
      expect(tasks).toEqual([]);
    });

    it('returns an empty array when parsing fails', () => {
      localStorage.setItem('todo-tasks', 'invalid json');
      const tasks = readTasks();
      expect(tasks).toEqual([]);
    });

    it('returns the tasks array from a valid JSON object', () => {
      const expectedTasks: Task[] = [
        {
          id: '1700000000000',
          title: 'Buy groceries',
          description: 'Milk and bread',
          completed: false,
        },
      ];
      localStorage.setItem(
        'todo-tasks',
        JSON.stringify({ tasks: expectedTasks })
      );

      const tasks = readTasks();
      expect(tasks).toEqual(expectedTasks);
    });

    it('returns an empty array if the parsed value does not have a tasks array', () => {
      localStorage.setItem('todo-tasks', JSON.stringify({ other: [] }));
      const tasks = readTasks();
      expect(tasks).toEqual([]);
    });
  });

  describe('saveTasks', () => {
    it('writes the tasks array to localStorage with the correct key and structure', () => {
      const tasks: Task[] = [
        {
          id: '1700000000000',
          title: 'Buy groceries',
          description: 'Milk and bread',
          completed: false,
        },
      ];

      saveTasks(tasks);

      const stored = localStorage.getItem('todo-tasks');
      expect(stored).toBe(JSON.stringify({ tasks }));
    });

    it('overwrites previous data with new tasks', () => {
      const initialTasks: Task[] = [
        {
          id: '1700000000000',
          title: 'Initial task',
          description: '',
          completed: false,
        },
      ];
      saveTasks(initialTasks);

      const updatedTasks: Task[] = [
        {
          id: '1700000000001',
          title: 'Updated task',
          description: '',
          completed: true,
        },
      ];
      saveTasks(updatedTasks);

      const stored = localStorage.getItem('todo-tasks');
      expect(stored).toBe(JSON.stringify({ tasks: updatedTasks }));
    });

    it('handles an empty array correctly', () => {
      saveTasks([]);

      const stored = localStorage.getItem('todo-tasks');
      expect(stored).toBe(JSON.stringify({ tasks: [] }));
    });
  });
});
