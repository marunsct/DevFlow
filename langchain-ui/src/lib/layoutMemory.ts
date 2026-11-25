/**
 * Layout choices remembered per browser (plan UX.1, UX.5): which rails of the run page are hidden, the workspace's
 * panel sizes. Storage can be missing or refused (a private window); the layout then simply starts as it does.
 */

export function remembered<T extends object>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? { ...fallback, ...parsed } : fallback;
  } catch {
    return fallback;
  }
}

export function remember(key: string, value: object): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Not kept: the next visit starts from the default layout.
  }
}

/** The run page's rails: the stages on the left, what is proven on the right. */
export interface Rails { left: boolean; right: boolean }
export const RAILS_KEY = 'runRails';
