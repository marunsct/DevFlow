import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RunNameField } from './RunNameField';
import { FeedbackProvider } from './Feedback';

const known = vi.hoisted(() => ({ setRunName: vi.fn() }));
vi.mock('../api', () => known);

const show = (props: Partial<React.ComponentProps<typeof RunNameField>> = {}) =>
  render(<FeedbackProvider><RunNameField runId="run-1" {...props} /></FeedbackProvider>);

describe('the run name', () => {
  beforeEach(() => {
    known.setRunName.mockReset();
    known.setRunName.mockResolvedValue({ run_id: 'run-1', run_name: 'x' });
  });

  it('invites a name when the run has none, and shows the name when it has one', () => {
    const { unmount } = show();
    expect(screen.getByText('Name this run')).toBeTruthy();
    unmount();
    show({ name: 'tasks-api on 8888' });
    expect(screen.getByText('tasks-api on 8888')).toBeTruthy();
  });

  it('saves what is typed on Enter, tidied, for its own run', async () => {
    const changed = vi.fn();
    show({ onChanged: changed });

    await userEvent.click(screen.getByRole('button'));
    await userEvent.type(screen.getByRole('textbox', { name: 'Run name' }), '  fix-loop   ON  {Enter}');

    await waitFor(() => expect(known.setRunName).toHaveBeenCalledWith('run-1', 'fix-loop ON'));
    await waitFor(() => expect(changed).toHaveBeenCalledWith('fix-loop ON'));
  });

  it('leaves the name as it was on Escape and sends nothing', async () => {
    show({ name: 'keep me' });

    await userEvent.click(screen.getByRole('button'));
    await userEvent.type(screen.getByRole('textbox', { name: 'Run name' }), ' changed{Escape}');

    expect(known.setRunName).not.toHaveBeenCalled();
    expect(screen.getByText('keep me')).toBeTruthy();
  });

  it('clears the name when it is emptied', async () => {
    show({ name: 'old' });

    await userEvent.click(screen.getByRole('button'));
    await userEvent.clear(screen.getByRole('textbox', { name: 'Run name' }));
    await userEvent.keyboard('{Enter}');

    await waitFor(() => expect(known.setRunName).toHaveBeenCalledWith('run-1', ''));
  });
});
