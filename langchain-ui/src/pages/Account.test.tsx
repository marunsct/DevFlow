import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { api } = vi.hoisted(() => ({ api: {
  get: vi.fn(async () => ({ data: [{ username: 'admin', role: 'admin', disabled: false }] })),
  post: vi.fn(async (path: string) => ({ data: path === '/users' ? { username: 'sam', password: 'p'.repeat(24) } : { message: 'ok' } })),
  patch: vi.fn(async () => ({ data: {} })),
} }));
vi.mock('../api', () => ({ api }));
import { MemoryRouter } from 'react-router-dom';
import { Account } from './Account';

// LR.36: accounts were made and passwords reset only from the command line.
describe('the account page', () => {
  it('changes your own password with the current one', async () => {
    render(<MemoryRouter><Account /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText('Current password'), 'first-one-123');
    await userEvent.type(screen.getByLabelText('New password'), 'second-one-1234');
    await userEvent.click(screen.getByText('Change it'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/auth/password', { current_password: 'first-one-123', new_password: 'second-one-1234' }));
  });

  it('lets an administrator add a person and shows their password once', async () => {
    render(<MemoryRouter><Account /></MemoryRouter>);
    expect(await screen.findByTestId('people')).toBeTruthy();
    await userEvent.type(screen.getByLabelText("New person's name"), 'sam');
    await userEvent.click(screen.getByText('Add'));
    expect(await screen.findByText(/sam's password, shown once/)).toBeTruthy();
  });
});
