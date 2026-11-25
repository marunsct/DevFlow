import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Editor, type EditorViewProps } from './Editor';

// Monaco itself does not run in a test's page; at its edge it is given what it would show.
vi.mock('./monaco', () => ({
  default: ({ path, text, diff }: EditorViewProps) => (
    <output aria-label="what the editor was given" data-path={path} data-now={text} data-base={diff?.base ?? ''} data-mode={diff ? 'diff' : 'read'} />
  ),
}));

describe('the workspace editor (plan UX.6)', () => {
  it('is given the text at the last accepted sprint and the text now for the side-by-side diff', async () => {
    render(<Editor path="src/app.py" text={"print('now')\n"} diff={{ base: "print('then')\n", since: 'sprint 1' }} />);

    const given = await screen.findByLabelText('what the editor was given');

    expect(given.dataset).toMatchObject({ path: 'src/app.py', mode: 'diff', base: "print('then')\n", now: "print('now')\n" });
  });

  it('reads a file without a change asked for', async () => {
    render(<Editor path="README.md" text="# The product" />);

    expect((await screen.findByLabelText('what the editor was given')).dataset).toMatchObject({ mode: 'read', now: '# The product' });
  });
});
