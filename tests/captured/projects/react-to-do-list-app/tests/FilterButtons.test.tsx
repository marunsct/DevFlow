import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FilterButtons from '../src/components/FilterButtons';
import type { FilterType } from '../src/types';

describe('FilterButtons', () => {
  const mockOnFilterChange = vi.fn();

  beforeEach(() => {
    mockOnFilterChange.mockClear();
  });

  it('renders three buttons: All, Active, Completed', () => {
    render(<FilterButtons currentFilter="all" onFilterChange={mockOnFilterChange} />);

    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Active' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Completed' })).toBeInTheDocument();
  });

  it('applies active styling to the current filter button', () => {
    render(<FilterButtons currentFilter="active" onFilterChange={mockOnFilterChange} />);

    const allButton = screen.getByRole('button', { name: 'All' });
    const activeButton = screen.getByRole('button', { name: 'Active' });
    const completedButton = screen.getByRole('button', { name: 'Completed' });

    expect(activeButton).toHaveStyle({ backgroundColor: '#2563eb', color: '#ffffff', fontWeight: 'bold' });
    expect(allButton).not.toHaveStyle({ backgroundColor: '#2563eb' });
    expect(completedButton).not.toHaveStyle({ backgroundColor: '#2563eb' });
  });

  it('calls onFilterChange with the correct filter value when a button is clicked', () => {
    render(<FilterButtons currentFilter="all" onFilterChange={mockOnFilterChange} />);

    const activeButton = screen.getByRole('button', { name: 'Active' });
    fireEvent.click(activeButton);

    expect(mockOnFilterChange).toHaveBeenCalledWith('active');
  });

  it('calls onFilterChange with "completed" when Completed button is clicked', () => {
    render(<FilterButtons currentFilter="all" onFilterChange={mockOnFilterChange} />);

    const completedButton = screen.getByRole('button', { name: 'Completed' });
    fireEvent.click(completedButton);

    expect(mockOnFilterChange).toHaveBeenCalledWith('completed');
  });

  it('calls onFilterChange with "all" when All button is clicked', () => {
    render(<FilterButtons currentFilter="active" onFilterChange={mockOnFilterChange} />);

    const allButton = screen.getByRole('button', { name: 'All' });
    fireEvent.click(allButton);

    expect(mockOnFilterChange).toHaveBeenCalledWith('all');
  });
});
