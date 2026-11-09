import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelCapabilitiesPanel, POLL_MS, type Capabilities } from './ModelCapabilitiesPanel';
import { FeedbackProvider } from './Feedback';

const capabilities = (overrides: Partial<Capabilities> = {}): Capabilities => ({
  model: 'LFM2.5-24B-A2B-GGUF',
  status: 'idle',
  message: '',
  fields: [
    { key: 'reads_images', label: 'Reads images', kind: 'bool', value: null, source: 'unknown',
      note: 'not measured yet', owner_value: null },
    { key: 'thinking_switch', label: 'Thinking switch', kind: 'choice', options: ['none', 'reasoning_effort', 'template'],
      value: 'none', source: 'measured', note: 'no switch changed its reasoning', owner_value: null },
    { key: 'context_window', label: 'Context window', kind: 'int', value: 131072, source: 'server',
      note: 'from /props', owner_value: null },
    { key: 'languages', label: 'Languages', kind: 'text', value: 'en, ja', source: 'owner',
      note: 'set on this page', owner_value: 'en, ja' },
  ],
  ...overrides,
});

const { get, post, put } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('../api', () => ({ api: { get, post, put } }));

const renderPanel = () => render(<FeedbackProvider><ModelCapabilitiesPanel /></FeedbackProvider>);

afterEach(() => {
  vi.useRealTimers();
  get.mockReset();
  post.mockReset();
  put.mockReset();
});

describe('the model capabilities panel', () => {
  it('shows each capability with its value and where it came from, and marks what is unknown', async () => {
    get.mockResolvedValue({ data: capabilities() });
    renderPanel();

    expect(await screen.findByText('Reads images')).toBeTruthy();
    expect(screen.getByText('unknown')).toBeTruthy();
    expect(screen.getByText('measured')).toBeTruthy();
    expect(screen.getByText('server')).toBeTruthy();
    expect(screen.getByText('owner')).toBeTruthy();
    expect(screen.getByText(/1 still unknown/)).toBeTruthy();
    expect((screen.getByLabelText('Context window value') as HTMLInputElement).value).toBe('131072');
    expect(screen.getByText('Reads images').closest('tr')?.getAttribute('data-unknown')).toBe('true');
    expect(get).toHaveBeenCalledWith('/settings/model/capabilities');
  });

  it('sends only the changed value when saved', async () => {
    get.mockResolvedValue({ data: capabilities() });
    put.mockResolvedValue({ data: capabilities() });
    renderPanel();

    await userEvent.selectOptions(await screen.findByLabelText('Reads images value'), 'yes');
    await userEvent.click(screen.getByRole('button', { name: 'Save capabilities' }));

    expect(put).toHaveBeenCalledWith('/settings/model/capabilities', { values: { reads_images: true } });
  });

  it('hands an owner value back to the harness', async () => {
    get.mockResolvedValue({ data: capabilities() });
    put.mockResolvedValue({ data: capabilities() });
    renderPanel();

    await userEvent.click(await screen.findByRole('button', { name: 'Languages: back to automatic' }));

    expect(put).toHaveBeenCalledWith('/settings/model/capabilities', { values: { languages: null } });
  });

  it('finds what is missing and asks again while it runs, then stops asking', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    get.mockResolvedValueOnce({ data: capabilities() });
    post.mockResolvedValue({ data: { status: 'running', message: 'Looking up what is missing.' } });
    get.mockResolvedValueOnce({ data: capabilities({ status: 'running', message: 'Asking the model whether it reads images.' }) });
    get.mockResolvedValueOnce({ data: capabilities() });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPanel();

    await user.click(await screen.findByRole('button', { name: 'Find what is missing' }));

    expect(post).toHaveBeenCalledWith('/settings/model/capabilities/fill');
    expect(await screen.findByText('Asking the model whether it reads images.')).toBeTruthy();
    expect(get).toHaveBeenCalledTimes(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    expect(get).toHaveBeenCalledTimes(3);

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3); });
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('says why when a run is live and the look-up cannot start', async () => {
    get.mockResolvedValue({ data: capabilities() });
    post.mockRejectedValue({ response: { status: 409, data: { detail: 'A run is using the model now; look it up between runs.' } } });
    renderPanel();

    await userEvent.click(await screen.findByRole('button', { name: 'Find what is missing' }));

    expect(await screen.findByText('A run is using the model now; look it up between runs.')).toBeTruthy();
  });
});
