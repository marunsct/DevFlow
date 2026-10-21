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
  });
});
