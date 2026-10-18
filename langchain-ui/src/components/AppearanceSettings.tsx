/**
 * Settings -> Appearance: the theme (three cards, each a live miniature of the
 * run page), the accent, and the density. A choice applies at once, is kept in
 * this browser, and follows the owner to other devices through their account.
 */
import React, { useSyncExternalStore } from 'react';
import {
  ACCENTS, DENSITIES, THEMES, getAppearance, setAppearance, subscribe,
  type Accent, type Density, type Theme,
} from '../lib/appearance';

const THEME_TEXT: Record<Theme, { name: string; note: string }> = {
  graphite: { name: 'Graphite', note: 'Dark, easy on the eyes in a dim room.' },
  paper: { name: 'Paper', note: 'Light, for a bright room or a projector.' },
  contrast: { name: 'High contrast', note: 'Black and white with strong borders (AAA).' },
  system: { name: 'Follow the system', note: 'Dark or light as the device is set.' },
};

/** The accent colours as they look on a dark and a light surface. */
const SWATCH: Record<Accent, string> = {
  blue: '#6e8bff', violet: '#9b7bff', teal: '#2fb8a8', amber: '#e0a030', rose: '#f0708f', neutral: '#c9ced8',
};

/** A miniature of the run page, painted with the theme's own tokens by scoping the attribute to the card. */
const Miniature: React.FC<{ theme: Theme }> = ({ theme }) => (
  <div
    data-theme={theme}
    aria-hidden="true"
    className="rounded-md overflow-hidden border"
    style={{ background: 'var(--bg-canvas)', borderColor: 'var(--border)', color: 'var(--fg)' }}
  >
    <div className="h-4 px-2 flex items-center gap-1" style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--accent)' }} />
      <span className="h-1 w-8 rounded" style={{ background: 'var(--fg-muted)' }} />
    </div>
    <div className="p-2 space-y-1.5">
      <div className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--status-ok-fg)' }} />
        <span className="h-1.5 w-16 rounded" style={{ background: 'var(--fg)' }} />
      </div>
      <div className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--status-warn-fg)' }} />
        <span className="h-1.5 w-12 rounded" style={{ background: 'var(--fg-muted)' }} />
      </div>
      <div className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--status-danger-fg)' }} />
        <span className="h-1.5 w-14 rounded" style={{ background: 'var(--fg-muted)' }} />
      </div>
      <div className="h-3 w-10 rounded" style={{ background: 'var(--accent)' }} />
    </div>
  </div>
);

export const AppearanceSettings: React.FC = () => {
  const current = useSyncExternalStore(subscribe, getAppearance);

  return (
    <section className="glass-card rounded-2xl p-5" aria-labelledby="appearance-heading">
      <h2 id="appearance-heading" className="text-base font-semibold text-text-primary">Appearance</h2>
      <p className="text-sm text-text-secondary mt-0.5 mb-4">
        Kept in this browser and on your account. The key <kbd className="px-1 rounded bg-overlay-strong text-[11px]">t</kbd> cycles the theme anywhere in the interface.
      </p>

      <fieldset>
        <legend className="text-sm font-medium text-text-primary mb-2">Theme</legend>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {THEMES.map((theme) => (
            <label
              key={theme}
              className={`cursor-pointer rounded-xl border p-2.5 transition-colors ${
                current.theme === theme ? 'border-primary bg-accent-soft' : 'border-border hover:border-border-strong'
              }`}
            >
              <input
                type="radio" name="theme" value={theme} className="sr-only"
                checked={current.theme === theme} onChange={() => setAppearance({ theme })}
              />
              <Miniature theme={theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'paper' : 'graphite') : theme} />
              <span className="block mt-2 text-sm font-medium text-text-primary">{THEME_TEXT[theme].name}</span>
              <span className="block text-xs text-text-secondary">{THEME_TEXT[theme].note}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="mt-5">
        <legend className="text-sm font-medium text-text-primary mb-2">Accent</legend>
        <div className="flex flex-wrap gap-2">
          {ACCENTS.map((accent) => (
            <label
              key={accent}
              className={`cursor-pointer inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                current.accent === accent ? 'border-primary bg-accent-soft text-text-primary' : 'border-border text-text-secondary hover:border-border-strong'
              }`}
            >
              <input
                type="radio" name="accent" value={accent} className="sr-only"
                checked={current.accent === accent} onChange={() => setAppearance({ accent })}
              />
              <span className="h-3 w-3 rounded-full border border-border-strong" style={{ background: SWATCH[accent] }} aria-hidden="true" />
              <span className="capitalize">{accent}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="mt-5">
        <legend className="text-sm font-medium text-text-primary mb-2">Density</legend>
        <div className="flex gap-2">
          {DENSITIES.map((density: Density) => (
            <label
              key={density}
              className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm capitalize transition-colors ${
                current.density === density ? 'border-primary bg-accent-soft text-text-primary' : 'border-border text-text-secondary hover:border-border-strong'
              }`}
            >
              <input
                type="radio" name="density" value={density} className="sr-only"
                checked={current.density === density} onChange={() => setAppearance({ density })}
              />
              {density}
            </label>
          ))}
        </div>
      </fieldset>
    </section>
  );
};
