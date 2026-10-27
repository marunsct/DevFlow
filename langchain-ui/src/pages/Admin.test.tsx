import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Admin, type SwitchEntry } from './Admin';
import { FeedbackProvider } from '../components/Feedback';

const entry = (overrides: Partial<SwitchEntry> = {}): SwitchEntry => ({
  name: 'START_PROBE',
  module: 'app.acceptance.start_probe',
  summary: 'When the product does not start for the suite, the harness starts it the same way and says what it saw.',
  details: 'Measured on a small-model run: the suite timed out for 40 minutes.',
  default: false,
  docker: true,
  setting: null,
  on: true,
  source: 'docker',
  ...overrides,
});

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('../api', () => ({ api: { get, put } }));

const serve = (switches: SwitchEntry[], role = 'admin') =>
  get.mockImplementation((url: string) =>
    Promise.resolve({ data: url === '/auth/me' ? { username: 'a', role } : switches }));

const renderPage = () => render(<FeedbackProvider><Admin /></FeedbackProvider>);

afterEach(() => {
  get.mockReset();
  put.mockReset();
});

describe('the admin page', () => {
  it('lists every switch with what it does, its value and where the value comes from', async () => {
    serve([entry(), entry({ name: 'MEASURE_ONCE', summary: 'A product measured by the suite is not measured again until it changes.', docker: null, on: false, source: 'default', details: '' })]);
    renderPage();

    expect(await screen.findByText('START_PROBE')).toBeTruthy();
    expect(screen.getByText(/starts it the same way and says what it saw/)).toBeTruthy();
    expect(screen.getByText('from Docker')).toBeTruthy();
    expect(screen.getByText('code default')).toBeTruthy();
    expect(screen.getByText('1 of 2 on, 0 set here')).toBeTruthy();
    const docker = screen.getByLabelText('MEASURE_ONCE value') as HTMLSelectElement;
    expect(docker.value).toBe('docker');
    expect(within(docker).getByText('Docker (not set: code default, off)')).toBeTruthy();
  });

  it('sets a switch, and sets it back to the Docker value', async () => {
    serve([entry()]);
    put.mockResolvedValueOnce({ data: [entry({ setting: false, on: false, source: 'setting' })] })
       .mockResolvedValueOnce({ data: [entry()] });
    renderPage();
    const select = (await screen.findByLabelText('START_PROBE value')) as HTMLSelectElement;
    await screen.findByText('1 of 1 on, 0 set here');
    await vi.waitFor(() => expect(select.disabled).toBe(false));

    await userEvent.selectOptions(select, 'off');
    expect(put).toHaveBeenCalledWith('/settings/switches/START_PROBE', { setting: false });
    expect(await screen.findByText('set here')).toBeTruthy();

    await userEvent.selectOptions(screen.getByLabelText('START_PROBE value'), 'docker');
    expect(put).toHaveBeenLastCalledWith('/settings/switches/START_PROBE', { setting: null });
  });

  it('is read-only for someone who is not an administrator, and finds a switch by what it does', async () => {
    serve([entry(), entry({ name: 'STALL_RULE', summary: 'A sprint whose attempts stop improving is not planned again and again.' })], 'user');
    renderPage();

    expect(await screen.findByText(/this view is read-only/)).toBeTruthy();
    expect((screen.getByLabelText('START_PROBE value') as HTMLSelectElement).disabled).toBe(true);

    await userEvent.type(screen.getByRole('searchbox'), 'planned again');
    expect(screen.queryByText('START_PROBE')).toBeNull();
    expect(screen.getByText('STALL_RULE')).toBeTruthy();
  });
});
