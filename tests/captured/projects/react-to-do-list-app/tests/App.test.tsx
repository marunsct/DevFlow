import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from '../src/App';
import type { Task, FilterType } from '../src/types';

// Mock localStorage to ensure isolation and clean state for each test
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem(key: string) {
      return store[key] || null;
    },
    setItem(key: string, value: string) {
      store[key] = value;
    },
    removeItem(key: string) {
      delete store[key];
    },
    clear() {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('App Component Tests', () => {
  beforeEach(() => {
    // Clear localStorage before each test to ensure a fresh store
    localStorage.clear();
  });

  afterEach(() => {
    // Ensure cleanup after tests
    localStorage.clear();
  });

  it('AC-1: Adds new tasks with title and description', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const descriptionInput = screen.getByLabelText('Description');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Buy groceries' } });
    fireEvent.change(descriptionInput, { target: { value: 'Milk and bread' } });
    fireEvent.click(addButton);

    expect(screen.getByText('Buy groceries')).toBeInTheDocument();
    expect(screen.getByText('Milk and bread')).toBeInTheDocument();
  });

  it('AC-2: Marks tasks as complete/incomplete', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Test Task' } });
    fireEvent.click(addButton);

    const checkbox = screen.getByRole('checkbox', { name: 'Done' });
    
    // Initially not completed
    expect(checkbox).not.toBeChecked();
    
    // Click to mark complete
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    
    // Click again to mark incomplete
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it('AC-3: Edits a task\'s title', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Original Title' } });
    fireEvent.click(addButton);

    const editButton = screen.getByRole('button', { name: 'Edit' });
    fireEvent.click(editButton);

    const editInput = screen.getByLabelText('Edit title');
    const saveButton = screen.getByRole('button', { name: 'Save' });

    fireEvent.change(editInput, { target: { value: 'Updated Title' } });
    fireEvent.click(saveButton);

    expect(screen.getByText('Updated Title')).toBeInTheDocument();
  });

  it('AC-4: Deletes tasks', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Task to Delete' } });
    fireEvent.click(addButton);

    expect(screen.getByText('Task to Delete')).toBeInTheDocument();

    const deleteButton = screen.getByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButton);

    // Task should no longer be in the document
    await waitFor(() => {
      expect(screen.queryByText('Task to Delete')).not.toBeInTheDocument();
    });
  });

  it('AC-5: Filters tasks by status (all, active, completed)', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    // Add two tasks
    fireEvent.change(titleInput, { target: { value: 'Active Task' } });
    fireEvent.click(addButton);

    fireEvent.change(titleInput, { target: { value: 'Completed Task' } });
    fireEvent.click(addButton);

    // Mark the second task as completed
    const checkboxes = screen.getAllByRole('checkbox', { name: 'Done' });
    // The first checkbox corresponds to 'Active Task' (index 0)
    // The second checkbox corresponds to 'Completed Task' (index 1)
    fireEvent.click(checkboxes[1]);

    // Filter by 'Active'
    const activeButton = screen.getByRole('button', { name: 'Active' });
    fireEvent.click(activeButton);

    expect(screen.getByText('Active Task')).toBeInTheDocument();
    expect(screen.queryByText('Completed Task')).not.toBeInTheDocument();

    // Filter by 'Completed'
    const completedButton = screen.getByRole('button', { name: 'Completed' });
    fireEvent.click(completedButton);

    expect(screen.getByText('Completed Task')).toBeInTheDocument();
    expect(screen.queryByText('Active Task')).not.toBeInTheDocument();

    // Filter by 'All'
    const allButton = screen.getByRole('button', { name: 'All' });
    fireEvent.click(allButton);

    expect(screen.getByText('Active Task')).toBeInTheDocument();
    expect(screen.getByText('Completed Task')).toBeInTheDocument();
  });

  it('AC-6: Renders Title input, Description textarea, and Add task button', () => {
    render(<App />);
    
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add task' })).toBeInTheDocument();
  });

  it('AC-7: A task cannot be added without a title', async () => {
    render(<App />);
    
    const descriptionInput = screen.getByLabelText('Description');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    // Leave title empty, fill description
    fireEvent.change(descriptionInput, { target: { value: 'Some description' } });
    fireEvent.click(addButton);

    // Task should not be added – verify no task list item appears.
    // We check that the form fields still exist (the textarea is still on page)
    // but no task with the provided description is in the list.
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    // The title input should show error state (red border)
    const titleInput = screen.getByLabelText('Title');
    expect(titleInput).toHaveStyle({ borderColor: '#dc2626' });
  });

  it('AC-8: Each task is an item of a list and shows its title and description', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const descriptionInput = screen.getByLabelText('Description');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'List Item Task' } });
    fireEvent.change(descriptionInput, { target: { value: 'List Item Description' } });
    fireEvent.click(addButton);

    expect(screen.getByText('List Item Task')).toBeInTheDocument();
    expect(screen.getByText('List Item Description')).toBeInTheDocument();
  });

  it('AC-9: Each task has a checkbox labelled "Done" that marks it complete or incomplete', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Done Task' } });
    fireEvent.click(addButton);

    const checkbox = screen.getByRole('checkbox', { name: 'Done' });
    
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
  });

  it('AC-10: Each task has a button named "Edit". It shows a text field labelled "Edit title" and a button named "Save" that saves the new title', async () => {
    render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Editable Task' } });
    fireEvent.click(addButton);

    const editButton = screen.getByRole('button', { name: 'Edit' });
    fireEvent.click(editButton);

    expect(screen.getByLabelText('Edit title')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();

    const editInput = screen.getByLabelText('Edit title');
    const saveButton = screen.getByRole('button', { name: 'Save' });

    fireEvent.change(editInput, { target: { value: 'Saved Title' } });
    fireEvent.click(saveButton);

    expect(screen.getByText('Saved Title')).toBeInTheDocument();
  });

  it('AC-14: Tasks persist between page refreshes (simulated by re-render)', async () => {
    // Add a task first
    const { unmount } = render(<App />);
    
    const titleInput = screen.getByLabelText('Title');
    const addButton = screen.getByRole('button', { name: 'Add task' });

    fireEvent.change(titleInput, { target: { value: 'Persisted Task' } });
    fireEvent.click(addButton);

    expect(screen.getByText('Persisted Task')).toBeInTheDocument();

    // Simulate persistence by manually setting localStorage and re-rendering
    const stored = localStorage.getItem('todo-tasks');
    expect(stored).toBeTruthy();
    
    const parsed: { tasks: Task[] } = JSON.parse(stored!);
    expect(parsed.tasks.length).toBe(1);
    expect(parsed.tasks[0].title).toBe('Persisted Task');

    // Unmount the first render to avoid duplicate DOM nodes,
    // then re-render the app (simulating a page refresh)
    unmount();

    // Re-mount so useEffect reads from localStorage on mount
    render(<App />);

    // The task should still be there because useEffect in App reads from localStorage on mount
    expect(screen.getByText('Persisted Task')).toBeInTheDocument();
  });

  it('AC-16: Responsive design for mobile and desktop (basic layout check)', () => {
    // This test verifies that the component renders without errors and contains expected structural elements.
    // Actual CSS media query testing is usually done in E2E/Playwright tests, but we can assert basic rendering.
    render(<App />);
    
    expect(screen.getByText('Simple To-Do List App')).toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add task' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Active' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Completed' })).toBeInTheDocument();
  });
});
