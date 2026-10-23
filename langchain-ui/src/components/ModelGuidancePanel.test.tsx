import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelGuidancePanel, POLL_MS, type Steering } from './ModelGuidancePanel';
import { FeedbackProvider } from './Feedback';

const steering = (overrides: Partial<Steering> = {}): Steering => ({
  model: 'LFM2.5-24B-A2B-GGUF',
  measured_at: '2026-10-23T09:30:00+00:00',
  status: 'idle',
  message: '',
  tier: 'weak',
  score: 0.58,
  checks: [
    { name: 'a plan answered in its schema', area: 'schemas', passed: 1, tries: 3 },
    { name: 'a role kept', area: 'roles', passed: 3, tries: 3 },
  ],
  guides: [
    {
      id: 'answer_in_schema', title: 'Answer in the schema', area: 'schemas',
      text: 'Give your answer as one call of your answer tool, never as text.',
      switch: 'GUIDE_ANSWER_IN_SCHEMA', switch_on: true, chosen: true, override: null, active: true,
    },
    {
      id: 'keep_to_the_role', title: 'Keep to the role', area: 'roles',
      text: 'Change only what your request names as yours.',
      switch: 'GUIDE_KEEP_TO_THE_ROLE', switch_on: false, chosen: false, override: null, active: false,
    },
  ],
  settings: { structured_answers: 'forced', reasoning_effort: '', reply_ceiling: 40000, tail_reminder: true },
  ...overrides,
});

const { get, post, put } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));
vi.mock('../api', () => ({ api: { get, post, put } }));

const renderPanel = () => render(<FeedbackProvider><ModelGuidancePanel /></FeedbackProvider>);

afterEach(() => {
  vi.useRealTimers();
  get.mockReset();
  post.mockReset();
  put.mockReset();
});

describe('the model guidance panel', () => {
  it('shows the tier, the checks and the guides with their switches', async () => {
    get.mockResolvedValue({ data: steering() });
    renderPanel();

    expect(await screen.findByText(/weak - full steering with reminders/)).toBeTruthy();
    expect(screen.getByText(/score 58%/)).toBeTruthy();
    expect(screen.getByText('a plan answered in its schema')).toBeTruthy();
    expect(screen.getByText('1/3')).toBeTruthy();
    expect(screen.getByText('Answer in the schema')).toBeTruthy();
    expect(screen.getByText('chosen by the diagnosis')).toBeTruthy();
    expect(screen.getByText(/off globally/)).toBeTruthy();
    expect(screen.getByText('40,000 tokens')).toBeTruthy();
    expect(get).toHaveBeenCalledWith('/settings/model/steering');
  });

  it('starts the diagnosis and asks again while it runs, then stops asking', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    get.mockResolvedValueOnce({ data: steering({ measured_at: null, tier: null, score: null, checks: [] }) });
    post.mockResolvedValue({ data: { status: 'running', message: 'The diagnosis has started.' } });
    get.mockResolvedValueOnce({ data: steering({ status: 'running', message: 'Asking the model its questions.' }) });
    get.mockResolvedValueOnce({ data: steering() });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPanel();

    await user.click(await screen.findByRole('button', { name: 'Diagnose this model and set its guidance' }));

    expect(post).toHaveBeenCalledWith('/settings/model/steering/diagnose');
    expect(await screen.findByText('Asking the model its questions.')).toBeTruthy();
    expect(get).toHaveBeenCalledTimes(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });

    expect(get).toHaveBeenCalledTimes(3);
    expect(await screen.findByText(/weak - full steering/)).toBeTruthy();

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3); });

    expect(get).toHaveBeenCalledTimes(3);
  });

  it('says why when a run is live and the diagnosis cannot start', async () => {
    get.mockResolvedValue({ data: steering() });
    post.mockRejectedValue({ response: { status: 409, data: { detail: 'A run is using the model now; diagnose it between runs.' } } });
    renderPanel();

    await userEvent.click(await screen.findByRole('button', { name: 'Diagnose this model and set its guidance' }));

    expect(await screen.findByText('A run is using the model now; diagnose it between runs.')).toBeTruthy();
  });

  it('sets a guide off for this model', async () => {
    get.mockResolvedValue({ data: steering() });
    const off = steering();
    off.guides[0] = { ...off.guides[0], override: false, active: false };
    put.mockResolvedValue({ data: off });
    renderPanel();

    await userEvent.selectOptions(await screen.findByLabelText('Answer in the schema for this model'), 'off');

    expect(put).toHaveBeenCalledWith('/settings/model/steering/guides/answer_in_schema', { override: false });
    expect((screen.getByLabelText('Answer in the schema for this model') as HTMLSelectElement).value).toBe('off');
  });

  it('shows nothing measured when the server has no steering yet', async () => {
    get.mockResolvedValue({ data: [] });
    renderPanel();

    expect(await screen.findByText('not measured')).toBeTruthy();
    expect(screen.queryByText('Guides')).toBeNull();
  });
});
