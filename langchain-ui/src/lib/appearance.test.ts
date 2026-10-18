import { beforeEach, describe, expect, it, vi } from 'vitest';
import { adoptServerPreferences, getAppearance, nextTheme, readAppearance, setAppearance } from './appearance';

vi.mock('../api', () => ({ api: { patch: vi.fn(async () => ({})), get: vi.fn(async () => ({ data: {} })) } }));

beforeEach(() => {
  setAppearance({ theme: 'graphite', accent: 'blue', density: 'comfortable' }, false);
  localStorage.clear();
});

describe('the appearance', () => {
  it('puts the choice on <html> and keeps it', () => {
    setAppearance({ theme: 'paper', accent: 'teal' }, false);

    const root = document.documentElement;
    expect(root.getAttribute('data-theme')).toBe('paper');
    expect(root.getAttribute('data-accent')).toBe('teal');
    expect(readAppearance()).toMatchObject({ theme: 'paper', accent: 'teal' });
  });

  it('removes the accent attribute for the default blue', () => {
    setAppearance({ accent: 'rose' }, false);
    setAppearance({ accent: 'blue' }, false);

    expect(document.documentElement.hasAttribute('data-accent')).toBe(false);
  });

  it('replaces anything unknown it finds saved', () => {
    localStorage.setItem('devflow.appearance', JSON.stringify({ theme: 'neon', accent: 7, density: 'tiny' }));

    expect(readAppearance()).toEqual({ theme: 'system', accent: 'blue', density: 'comfortable' });
  });

  it('cycles dark, light, high contrast, system', () => {
    expect(['graphite', 'paper', 'contrast', 'system'].map((t) => nextTheme(t as never))).toEqual(
      ['paper', 'contrast', 'system', 'graphite'],
    );
  });

  it("takes the server's saved choice over its own, and ignores values it does not know", () => {
    adoptServerPreferences({ theme: 'contrast', accent: 'amber', density: 'sideways' });

    expect(getAppearance()).toMatchObject({ theme: 'contrast', accent: 'amber', density: 'comfortable' });
    expect(document.documentElement.getAttribute('data-theme')).toBe('contrast');
  });

  it('sends a change to the account', async () => {
    const { api } = await import('../api');
    setAppearance({ density: 'compact' });

    await vi.waitFor(() => expect(api.patch).toHaveBeenCalledWith('/auth/me/preferences', { density: 'compact' }));
  });
});
