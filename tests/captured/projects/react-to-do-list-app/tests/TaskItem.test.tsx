import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TaskItem from '../src/components/TaskItem';
import type { Task } from '../src/types';

describe('TaskItem', () => {
  const baseTask: Task = {
    id: '1',
    title: 'Test Task',
    description: 'A test task description',
    completed: false,
  };

  // Helper to render TaskItem with default mock callbacks.
  // The component's interface accepts these props for external coordination;
  // tests pass vi.fn() stubs and assert they are called correctly.
  const renderTaskItem = (task: Task, overrides?: Partial<TaskItemProps>) => {
    const defaultProps: TaskItemProps = {
      task,
      isEditing: false,
      editValue: '',
      onToggle: vi.fn(),
      onDelete: vi.fn(),
      onEditStart: vi.fn(),
      onSaveEdit: vi.fn(),
      onCancelEdit: vi.fn(),
      onEditInputChange: vi.fn(),
      ...overrides,
    };
    return render(<TaskItem {...defaultProps} />);
  };

  // ── checkbox toggling ──────────────────────────────────────────────

  describe('checkbox toggling', () => {
    it('calls onToggle when the Done checkbox is clicked', () => {
      const onToggle = vi.fn();
      renderTaskItem(baseTask, { onToggle });

      const checkbox = screen.getByLabelText('Done');
      fireEvent.click(checkbox);

      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it('shows line-through and reduced opacity when task is completed', () => {
      const completedTask = { ...baseTask, completed: true };
      renderTaskItem(completedTask);

      const titleText = screen.getByText(baseTask.title);
      expect(titleText).toHaveStyle({
        textDecoration: 'line-through',
        opacity: 0.6,
      });
    });
  });

  // ── edit/save workflow (contract: internal state) ──────────────────
  // The contract specifies TaskItem manages isEditing/editValue locally:
  // clicking "Edit" reveals the inline input labelled "Edit title" and a
  // "Save" button; pressing Escape cancels; saving with an empty title
  // shows a red border without calling onSaveEdit.

  describe('edit/save workflow', () => {
    it('shows Edit button in view mode', () => {
      renderTaskItem(baseTask);

      expect(screen.getByLabelText('Edit')).toBeInTheDocument();
      expect(screen.getByLabelText('Delete')).toBeInTheDocument();
      expect(screen.queryByLabelText('Edit title')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Save')).not.toBeInTheDocument();
    });

    it('clicking Edit reveals the "Edit title" input and Save button', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      expect(screen.getByLabelText('Edit title')).toBeInTheDocument();
      expect(screen.getByLabelText('Save')).toBeInTheDocument();
    });

    it('the "Edit title" input is pre-filled with the task title', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      expect(editInput).toHaveValue('Test Task');
    });

    it('calls onSaveEdit with new title when Save is clicked', () => {
      const onSaveEdit = vi.fn();
      renderTaskItem(baseTask, { onSaveEdit });

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      fireEvent.change(editInput, { target: { value: 'Updated Task' } });

      const saveButton = screen.getByLabelText('Save');
      fireEvent.click(saveButton);

      expect(onSaveEdit).toHaveBeenCalledWith('Updated Task');
    });

    it('rejects empty title on save and shows red border', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      fireEvent.change(editInput, { target: { value: '' } });

      const saveButton = screen.getByLabelText('Save');
      fireEvent.click(saveButton);

      expect(editInput).toHaveStyle({ borderColor: 'rgb(220, 38, 38)' }); // #dc2626
    });

    it('does not call onSaveEdit when saving an empty title', () => {
      const onSaveEdit = vi.fn();
      renderTaskItem(baseTask, { onSaveEdit });

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      fireEvent.change(editInput, { target: { value: '' } });

      const saveButton = screen.getByLabelText('Save');
      fireEvent.click(saveButton);

      expect(onSaveEdit).not.toHaveBeenCalled();
    });

    it('calls onCancelEdit when Escape is pressed in edit mode', () => {
      const onCancelEdit = vi.fn();
      renderTaskItem(baseTask, { onCancelEdit });

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      fireEvent.keyDown(editInput, { key: 'Escape' });

      expect(onCancelEdit).toHaveBeenCalledTimes(1);
    });

    it('returns to view mode after Save with a valid title', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      fireEvent.change(editInput, { target: { value: 'New Title' } });

      const saveButton = screen.getByLabelText('Save');
      fireEvent.click(saveButton);

      expect(screen.queryByLabelText('Edit title')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Save')).not.toBeInTheDocument();
      expect(screen.getByText('New Title')).toBeInTheDocument();
    });
  });

  // ── delete button ──────────────────────────────────────────────────

  describe('delete button', () => {
    it('calls onDelete when Delete button is clicked', () => {
      const onDelete = vi.fn();
      renderTaskItem(baseTask, { onDelete });

      const deleteButton = screen.getByLabelText('Delete');
      fireEvent.click(deleteButton);

      expect(onDelete).toHaveBeenCalledTimes(1);
    });
  });

  // ── inline editing validation ──────────────────────────────────────

  describe('inline editing validation', () => {
    it('shows invalid state when saving whitespace-only title', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      fireEvent.change(editInput, { target: { value: '   ' } });

      const saveButton = screen.getByLabelText('Save');
      fireEvent.click(saveButton);

      expect(editInput).toHaveStyle({ borderColor: 'rgb(220, 38, 38)' });
    });

    it('clears invalid state when user types a non-empty value after rejection', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      const editInput = screen.getByLabelText('Edit title');
      // Trigger invalid state first
      fireEvent.change(editInput, { target: { value: '' } });
      const saveButton = screen.getByLabelText('Save');
      fireEvent.click(saveButton);

      // Now type a valid value – red border should be removed
      fireEvent.change(editInput, { target: { value: 'Valid Title' } });

      expect(editInput).not.toHaveStyle({ borderColor: 'rgb(220, 38, 38)' });
    });

    it('hides Edit/Delete buttons and shows Save when in edit mode', () => {
      renderTaskItem(baseTask);

      const editButton = screen.getByLabelText('Edit');
      fireEvent.click(editButton);

      expect(screen.queryByLabelText('Edit')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Delete')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Save')).toBeInTheDocument();
    });
  });
});
