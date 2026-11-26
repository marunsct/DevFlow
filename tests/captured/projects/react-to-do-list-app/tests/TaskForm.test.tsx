import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TaskForm from '../src/components/TaskForm';

describe('TaskForm', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const mockOnAdd = vi.fn();
  const mockOnTitleChange = vi.fn();
  const mockOnDescriptionChange = vi.fn();

  it('renders Title input, Description textarea, and Add task button', () => {
    render(
      <TaskForm
        title=""
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add task' })).toBeInTheDocument();
  });

  it('updates title input value on change', () => {
    render(
      <TaskForm
        title=""
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    const input = screen.getByLabelText('Title');
    fireEvent.change(input, { target: { value: 'New Task' } });

    expect(mockOnTitleChange).toHaveBeenCalledWith('New Task');
  });

  it('updates description textarea value on change', () => {
    render(
      <TaskForm
        title=""
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    const textarea = screen.getByLabelText('Description');
    fireEvent.change(textarea, { target: { value: 'New Description' } });

    expect(mockOnDescriptionChange).toHaveBeenCalledWith('New Description');
  });

  it('does not call onAdd when title is empty', () => {
    render(
      <TaskForm
        title=""
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    const button = screen.getByRole('button', { name: 'Add task' });
    fireEvent.click(button);

    expect(mockOnAdd).not.toHaveBeenCalled();
  });

  it('shows red border on Title input when adding with empty title', () => {
    render(
      <TaskForm
        title=""
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    const input = screen.getByLabelText('Title');
    const button = screen.getByRole('button', { name: 'Add task' });

    // Initially no error style
    expect(input.style.borderColor).not.toBe('2px solid #dc2626');

    fireEvent.click(button);

    // After click with empty title, should have red border
    expect(input.style.borderColor).toBe('rgb(220, 38, 38)');
  });

  it('calls onAdd when title is non-empty', () => {
    render(
      <TaskForm
        title="Valid Task"
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    const button = screen.getByRole('button', { name: 'Add task' });
    fireEvent.click(button);

    expect(mockOnAdd).toHaveBeenCalled();
  });

  it('clears error state when user types in title', () => {
    render(
      <TaskForm
        title=""
        description=""
        onTitleChange={mockOnTitleChange}
        onDescriptionChange={mockOnDescriptionChange}
        onAdd={mockOnAdd}
      />
    );

    const input = screen.getByLabelText('Title');
    const button = screen.getByRole('button', { name: 'Add task' });

    // Trigger error state
    fireEvent.click(button);
    expect(input.style.borderColor).toBe('rgb(220, 38, 38)');

    // Type valid title
    fireEvent.change(input, { target: { value: 'Valid Task' } });

    // Error state should be cleared
    expect(input.style.borderColor).not.toBe('rgb(220, 38, 38)');
  });
});
