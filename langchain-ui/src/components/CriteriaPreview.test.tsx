import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CriteriaPreview } from './CriteriaPreview';

const { previewBrief } = vi.hoisted(() => ({ previewBrief: vi.fn() }));
vi.mock('../api', () => ({ previewBrief }));

describe('the brief preview', () => {
  it('says which criteria the run would guess and which phrases ask for an unnamed quality', async () => {
    previewBrief.mockResolvedValue({
      criteria: [{ id: 'AC-1', text: 'Sign in' }, { id: 'AC-2', text: 'Search notes' }],
      from_brief: true, without_an_interface_line: ['AC-2'], vague_phrases: ['modern', 'properly'],
    });
    render(<CriteriaPreview brief="# Brief\n- Sign in\n- Search notes" />);

    expect((await screen.findByTestId('no-interface-line')).textContent).toContain('1 of 2 criteria');
    expect(screen.getByTestId('vague-phrases').textContent).toContain('modern, properly');
    expect(screen.queryByTestId('stack-experimental')).toBeNull();
  });

  // Deep review 2026-11-18, F1: nothing said before a run that its stack had too few scored runs here.
  it('warns before the run when the brief asks for an experimental stack', async () => {
    previewBrief.mockResolvedValue({
      criteria: [{ id: 'AC-1', text: 'Add a note' }, { id: 'AC-2', text: 'Delete a note' }],
      from_brief: true, without_an_interface_line: [], vague_phrases: [],
      stack_support: { status: 'experimental', languages: ['go'], said: 'The brief asks for go: experimental here.' },
    });
    render(<CriteriaPreview brief="# Brief\n- Add a note\n- Delete a note" />);

    expect((await screen.findByTestId('stack-experimental')).textContent).toContain('experimental here');
  });
});
