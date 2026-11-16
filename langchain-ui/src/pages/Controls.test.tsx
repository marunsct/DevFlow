import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Controls } from './Controls';

// LR.37: the owner's controls were each on a different page, and some on none.
describe('the controls page', () => {
  it('names every control the owner keeps', () => {
    render(<MemoryRouter><Controls /></MemoryRouter>);
    for (const name of [/instruction injection/, /Parallel or linear/, /Sprint Record/, /Work orders/, /Document templates/, /Switches/, /Model diagnosis/]) {
      expect(screen.getByText(name)).toBeTruthy();
    }
  });
});
