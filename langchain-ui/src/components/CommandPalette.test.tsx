import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { CommandPalette } from './CommandPalette';
import { FeedbackProvider } from './Feedback';
import { aRun } from '../test/runs';
import { matchCommands, type Command } from '../lib/commands';

const { listRuns, submitApproval, submitReview } = vi.hoisted(() => ({
  listRuns: vi.fn(),
  submitApproval: vi.fn(async () => ({ message: 'ok' })),
  submitReview: vi.fn(async () => ({ message: 'ok' })),
}));
vi.mock('../api', () => ({ listRuns, submitApproval, submitReview }));

const Where = () => <output aria-label="where">{useLocation().pathname}</output>;

const show = () =>
  render(
    <MemoryRouter initialEntries={['/runs']}>
      <FeedbackProvider>
        <CommandPalette />
        <Routes><Route path="*" element={<Where />} /></Routes>
      </FeedbackProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  listRuns.mockReset();
  submitApproval.mockClear();
  listRuns.mockResolvedValue({ runs: [aRun('run-8b0c41d2-aaaa', 'waiting_for_approval'), aRun('run-77aa01bc-bbbb', 'running')], total: 2 });
});

describe('the command palette', () => {
  it('opens on Ctrl K with the search focused, finds a command by a word of it, and runs it on Enter', async () => {
    show();
    await userEvent.keyboard('{Control>}k{/Control}');

    const search = screen.getByRole('combobox', { name: 'Find a command or a run' });
    expect(document.activeElement).toBe(search);

    await userEvent.type(search, 'settings');
    await userEvent.keyboard('{Enter}');

    expect(screen.getByLabelText('where').textContent).toBe('/settings');
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('goes to a run, moving to it with the arrow keys', async () => {
    show();
    await userEvent.keyboard('{Control>}k{/Control}');
    await userEvent.type(screen.getByRole('combobox'), 'go to');
    expect(await screen.findByRole('option', { name: /Go to run-77aa01bc/ })).toBeTruthy();

    await userEvent.keyboard('{ArrowDown}{Enter}');

    expect(screen.getByLabelText('where').textContent).toBe('/runs/run-77aa01bc-bbbb');
  });

  it('approves the waiting gate', async () => {
    show();
    await userEvent.keyboard('{Control>}k{/Control}');
    await userEvent.type(screen.getByRole('combobox'), 'approve');
    await screen.findByRole('option', { name: /Approve run-8b0c41d2/ });

    await userEvent.keyboard('{Enter}');

    expect(submitApproval).toHaveBeenCalledWith('run-8b0c41d2-aaaa', { action: 'approve', reason: null });
  });
});

describe('the shortcuts sheet', () => {
  it('opens on ?, but not while typing in a field', async () => {
    render(
      <MemoryRouter>
        <FeedbackProvider>
          <input aria-label="a field" />
          <CommandPalette />
        </FeedbackProvider>
      </MemoryRouter>,
    );

    await userEvent.type(screen.getByLabelText('a field'), '?');
    expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).toBeNull();

    (document.activeElement as HTMLElement).blur();
    await userEvent.keyboard('?');
    expect(screen.getByRole('dialog', { name: 'Keyboard shortcuts' }).textContent).toMatch(/Switch the theme/);
  });
});

describe('matching a query', () => {
  const command = (title: string, keywords = ''): Command => ({ id: title, title, keywords, run: () => undefined });

  it('needs every word, and puts a title that starts with the query first', () => {
    const commands = [command('Switch the theme', 'dark light'), command('Settings', 'model'), command('Start a build')];
    expect(matchCommands(commands, 'dark').map((c) => c.title)).toEqual(['Switch the theme']);
    expect(matchCommands(commands, 's').map((c) => c.title)[0]).toBe('Switch the theme');
    expect(matchCommands([command('Go to run-1', 'settings'), command('Settings')], 'settings').map((c) => c.title)).toEqual(['Settings', 'Go to run-1']);
    expect(matchCommands(commands, 'start nothing')).toEqual([]);
  });
});
