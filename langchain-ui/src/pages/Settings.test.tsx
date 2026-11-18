/**
 * A key typed into Settings keeps its focus (plan UI-P, H2). The credential
 * field was a component defined inside the Settings render, so each keystroke
 * made a new component type: React replaced the input and its focus went with
 * it after the first character.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { FeedbackProvider } from '../components/Feedback';
import { Settings } from './Settings';
import * as api from '../api';

const settings = {
  llm_provider: 'openai', openai_base_url: 'http://localhost:8888/v1', model_name: 'local-model',
  model_context_window: 32000, model_max_output_tokens: 0, openai_api_key_configured: false,
  judgement_api_key_configured: false, endpoint_key_saved: false,
};

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../api', () => ({
  api: { get, post: vi.fn(async () => ({ data: {} })), put: vi.fn(async () => ({ data: {} })), patch: vi.fn(async () => ({ data: {} })),
         delete: vi.fn(async () => ({ data: {} })) },
  saveLocalModelSettings: vi.fn(), saveFrontierModelSettings: vi.fn(),
}));

// jsdom has no media queries; the appearance panel asks for the system's scheme.
window.matchMedia = window.matchMedia || ((query: string) => ({
  matches: false, media: query, onchange: null,
  addEventListener: () => undefined, removeEventListener: () => undefined,
  addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

describe('Settings', () => {
  it('keeps the focus in a key field while a key is typed', async () => {
    get.mockImplementation(async (url: string) => {
      if (url === '/settings') return { data: settings };
      if (url === '/auth/me') return { data: { username: 'operator', role: 'operator' } };
      if (url.startsWith('/lessons')) return { data: { lessons: [] } };
      return { data: [] };
    });
    render(<MemoryRouter><FeedbackProvider><Settings /></FeedbackProvider></MemoryRouter>);

    const field = await screen.findByLabelText('API key');
    await userEvent.click(field);
    await userEvent.keyboard('sk-local');

    expect(document.activeElement).toBe(screen.getByLabelText('API key'));
    expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('sk-local');
  });

  it('saves the parallel choice with the model, so the save does not put linear back', async () => {
    get.mockImplementation(async (url: string) => {
      if (url === '/settings') return { data: { ...settings, execution_mode: 'linear' } };
      if (url === '/auth/me') return { data: { username: 'admin', role: 'admin' } };
      if (url.startsWith('/lessons')) return { data: { lessons: [] } };
      return { data: [] };
    });
    const save = vi.mocked(api.saveLocalModelSettings);
    save.mockResolvedValue({ ...settings, execution_mode: 'parallel' } as never);
    render(<MemoryRouter><FeedbackProvider><Settings /></FeedbackProvider></MemoryRouter>);

    await userEvent.click(await screen.findByRole('button', { name: /Parallel/ }));
    await userEvent.click(screen.getByRole('button', { name: /Save Local Model/ }));

    expect(save).toHaveBeenCalledWith(expect.objectContaining({ execution_mode: 'parallel' }));
  });

  it('puts the active frontier model back in the form after a saved one is deleted, so a save cannot restore it', async () => {
    // Found by the owner: choosing a saved frontier model to delete it filled the form with it, and the next save
    // brought it back as the active model.
    let deleted = false;
    const active = { ...settings, judgement_provider: 'anthropic', judgement_model_name: 'claude-haiku-5-5' };
    const saved = { id: 'p1', label: 'old-frontier (local)', target: 'frontier', judgement_model_name: 'old-frontier' };
    get.mockImplementation(async (url: string) => {
      if (url === '/settings') return { data: active };
      if (url === '/auth/me') return { data: { username: 'admin', role: 'admin' } };
      if (url.startsWith('/lessons')) return { data: { lessons: [] } };
      if (url === '/settings/models?target=frontier') return { data: deleted ? [] : [saved] };
      return { data: [] };
    });
    vi.mocked(api.api.delete).mockImplementation(async () => { deleted = true; return { data: {} } as never; });
    render(<MemoryRouter><FeedbackProvider><Settings /></FeedbackProvider></MemoryRouter>);

    const list = await screen.findByLabelText('Saved Frontier Models');
    await screen.findByRole('option', { name: /old-frontier/ });
    await userEvent.selectOptions(list, 'p1');
    expect(screen.getAllByLabelText('Model name').some(f => (f as HTMLInputElement).value === 'old-frontier')).toBe(true);

    await userEvent.click(screen.getByRole('button', { name: 'Remove this saved frontier model' }));

    await vi.waitFor(() => {
      const values = screen.getAllByLabelText('Model name').map(f => (f as HTMLInputElement).value);
      expect(values).toContain('claude-haiku-5-5');
      expect(values).not.toContain('old-frontier');
    });
  });
});
