/**
 * The owner's appearance: theme, accent and density, set on <html> as
 * data attributes (src/index.css reads them) and kept in localStorage. The
 * inline script in index.html applies the saved choice before first paint;
 * this keeps it in step afterwards and lets the interface change it.
 */
export const THEMES = ['graphite', 'paper', 'contrast', 'system'] as const;
export const ACCENTS = ['blue', 'violet', 'teal', 'amber', 'rose', 'neutral'] as const;
export const DENSITIES = ['comfortable', 'compact'] as const;

export type Theme = (typeof THEMES)[number];
export type Accent = (typeof ACCENTS)[number];
export type Density = (typeof DENSITIES)[number];

export interface Appearance {
  theme: Theme;
  accent: Accent;
  density: Density;
}

export const DEFAULT_APPEARANCE: Appearance = { theme: 'system', accent: 'blue', density: 'comfortable' };

const KEY = 'devflow.appearance';

const pick = <T extends string>(allowed: readonly T[], value: unknown, fallback: T): T =>
  allowed.includes(value as T) ? (value as T) : fallback;

/** Whatever was saved, with anything unknown replaced by the default. */
export function readAppearance(): Appearance {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
    return {
      theme: pick(THEMES, saved.theme, DEFAULT_APPEARANCE.theme),
      accent: pick(ACCENTS, saved.accent, DEFAULT_APPEARANCE.accent),
      density: pick(DENSITIES, saved.density, DEFAULT_APPEARANCE.density),
    };
  } catch {
    return DEFAULT_APPEARANCE;
  }
}

/** Whether the theme in effect is a dark one (for the browser's chrome colour). */
export function isDark(theme: Theme): boolean {
  if (theme === 'paper') return false;
  if (theme === 'system') return !window.matchMedia('(prefers-color-scheme: light)').matches;
  return true;
}

const CHROME: Record<string, string> = { graphite: '#15171c', paper: '#f4f5f7', contrast: '#000000' };

/** Put an appearance on the page and, unless told not to, keep it. */
export function applyAppearance(next: Appearance, save = true): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', next.theme);
  if (next.accent === 'blue') root.removeAttribute('data-accent');
  else root.setAttribute('data-accent', next.accent);
  root.setAttribute('data-density', next.density);
  const meta = document.querySelector('meta[name="theme-color"]');
  meta?.setAttribute('content', CHROME[next.theme] ?? (isDark(next.theme) ? CHROME.graphite : CHROME.paper));
  if (save) {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* storage may be unavailable; the choice holds for this visit */
    }
  }
}

/** The next theme when the header toggle is pressed: dark, light, high contrast, then the system's. */
export function nextTheme(current: Theme): Theme {
  const order: Theme[] = ['graphite', 'paper', 'contrast', 'system'];
  return order[(order.indexOf(current) + 1) % order.length];
}
