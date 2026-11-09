import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelSamplingPanel, SETTING_HELP, type Sampling } from './ModelSamplingPanel';
import { FeedbackProvider } from './Feedback';

const SETTINGS = ['temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty', 'repetition_penalty'];

const sampling = (overrides: Partial<Sampling> = {}): Sampling => ({
  model: 'qwen3.6-35b-a3b-mtp',
  settings: SETTINGS,
  determined_at: '2026-11-09T06:20:00+00:00',
  choices: { send: false, thinking_calls: 'thinking_precise' },
  modes: [
    { id: 'thinking_precise', label: 'Thinking - precise', used_for: 'Calls that reason first and write code.',
      what_it_does: 'Low randomness.', values: { temperature: 0.6, top_p: 0.95, top_k: 20 }, derived: { temperature: 0.6 },
      source: 'model card', note: "the card's settings for this mode", owner_set: false },
    { id: 'thinking_general', label: 'Thinking - general', used_for: 'Calls that reason and answer in prose.',
      what_it_does: 'More varied wording.', values: { temperature: 1.0 }, derived: { temperature: 1.0 },
      source: 'model card', note: "the card's settings for this mode", owner_set: false },
    { id: 'no_thinking', label: 'No thinking', used_for: 'Calls sent with thinking switched off.',
      what_it_does: 'Answers straight away.', values: { temperature: 0.2 }, derived: { temperature: 0.7 },
      source: 'owner', note: 'set on this page', owner_set: true },
  ],
  ...overrides,
});

const { get, post, put } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('../api', () => ({ api: { get, post, put } }));

const renderPanel = () => render(<FeedbackProvider><ModelSamplingPanel /></FeedbackProvider>);

afterEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
});

describe('the sampling by mode panel', () => {
  it('explains each mode, each setting and where every value came from', async () => {
    get.mockResolvedValue({ data: sampling() });
    renderPanel();

    expect(await screen.findByRole('article', { name: 'Thinking - precise' })).toBeTruthy();
    expect(screen.getByText('Calls that reason first and write code.')).toBeTruthy();
    expect(screen.getAllByText(SETTING_HELP.presence_penalty).length).toBe(3);
    expect(screen.getAllByText('model card').length).toBe(2);
    expect(screen.getByText('owner')).toBeTruthy();
    expect(screen.getByText('determined: 0.7')).toBeTruthy();
    expect((screen.getByLabelText('Thinking - precise temperature') as HTMLInputElement).value).toBe('0.6');
    expect(screen.getByText(/Off: nothing is sent/)).toBeTruthy();
    expect(get).toHaveBeenCalledWith('/settings/model/sampling');
  });

  it('marks which modes are in use: the chosen thinking mode and no thinking', async () => {
    get.mockResolvedValue({ data: sampling() });
    renderPanel();

    expect((await screen.findByRole('article', { name: 'Thinking - precise' })).getAttribute('data-used')).toBe('true');
    expect(screen.getByRole('article', { name: 'Thinking - general' }).getAttribute('data-used')).toBeNull();
    expect(screen.getByRole('article', { name: 'No thinking' }).getAttribute('data-used')).toBe('true');
  });

  it('determines the sampling on request', async () => {
    get.mockResolvedValue({ data: sampling({ determined_at: '' }) });
    post.mockResolvedValue({ data: sampling() });
    renderPanel();

    expect(await screen.findByText(/not determined yet/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Determine sampling' }));
    expect(post).toHaveBeenCalledWith('/settings/model/sampling/determine');
    expect(await screen.findByText(/determined 2026-11-09/)).toBeTruthy();
  });

  it('saves one mode with every setting, an emptied one as the server default', async () => {
    get.mockResolvedValue({ data: sampling() });
    put.mockResolvedValue({ data: sampling() });
    renderPanel();

    const temperature = await screen.findByLabelText('Thinking - precise temperature');
    await userEvent.clear(temperature);
    await userEvent.type(temperature, '0.5');
    await userEvent.clear(screen.getByLabelText('Thinking - precise top_k'));
    await userEvent.click(screen.getByRole('button', { name: 'Save Thinking - precise' }));

    expect(put).toHaveBeenCalledWith('/settings/model/sampling', {
      mode: 'thinking_precise',
      values: { temperature: 0.5, top_p: 0.95, top_k: null, min_p: null, presence_penalty: null, repetition_penalty: null },
    });
  });

  it('turns sending on, chooses the thinking mode and gives a mode back to what was determined', async () => {
    get.mockResolvedValue({ data: sampling() });
    put.mockResolvedValue({ data: sampling() });
    renderPanel();

    await userEvent.click(await screen.findByLabelText('Send sampling by mode'));
    expect(put).toHaveBeenCalledWith('/settings/model/sampling', { send: true });
    await userEvent.selectOptions(screen.getByLabelText('Mode for calls with thinking on'), 'thinking_general');
    expect(put).toHaveBeenCalledWith('/settings/model/sampling', { thinking_calls: 'thinking_general' });
    await userEvent.click(screen.getByRole('button', { name: 'Back to determined' }));
    expect(put).toHaveBeenCalledWith('/settings/model/sampling', { mode: 'no_thinking', values: null });
  });

  it('says so when no model is serving', async () => {
    get.mockResolvedValue({ data: sampling({ model: '', modes: [] }) });
    renderPanel();
    expect(await screen.findByText('No model is serving.')).toBeTruthy();
  });
});
