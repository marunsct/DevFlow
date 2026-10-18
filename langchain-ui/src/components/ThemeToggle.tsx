/** One press cycles the theme (dark, light, high contrast, the system's); the key `t` does the same. */
import React, { useEffect, useSyncExternalStore } from 'react';
import { Moon, Sun, Contrast, Monitor } from 'lucide-react';
import { getAppearance, nextTheme, setAppearance, subscribe, type Theme } from '../lib/appearance';

const LABEL: Record<Theme, string> = {
  graphite: 'Dark theme',
  paper: 'Light theme',
  contrast: 'High-contrast theme',
  system: 'Follows the system',
};
const ICON: Record<Theme, React.ElementType> = { graphite: Moon, paper: Sun, contrast: Contrast, system: Monitor };

const typing = (target: EventTarget | null): boolean => {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
};

export const ThemeToggle: React.FC = () => {
  const theme = useSyncExternalStore(subscribe, () => getAppearance().theme);
  const Icon = ICON[theme];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 't' || event.metaKey || event.ctrlKey || event.altKey || typing(event.target)) return;
      setAppearance({ theme: nextTheme(getAppearance().theme) });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <button
      type="button"
      onClick={() => setAppearance({ theme: nextTheme(theme) })}
      title={`${LABEL[theme]} - press to change (key t)`}
      aria-label={`${LABEL[theme]}. Change theme`}
      className="flex items-center justify-center h-9 w-9 rounded-lg text-text-secondary hover:text-text-primary hover:bg-overlay transition-colors"
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </button>
  );
};
