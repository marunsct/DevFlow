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

const settings = {
  llm_provider: 'openai', openai_base_url: 'http://localhost:8888/v1', model_name: 'local-model',
  model_context_window: 32000, model_max_output_tokens: 0, openai_api_key_configured: false,
  judgement_api_key_configured: false, endpoint_key_saved: false,
};

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../api', () => ({
  api: { get, post: vi.fn(async () => ({ data: {} })), put: vi.fn(async () => ({ data: {} })), patch: vi.fn(async () => ({ data: {} })) },
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
});
