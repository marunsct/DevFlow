/** What can take focus inside `root`, in order. */
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function focusables(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((node) => !node.hasAttribute('hidden'));
}

/** Keeps Tab and Shift+Tab inside `root`; true when it moved the focus. */
export function trapTab(event: KeyboardEvent, root: HTMLElement | null): boolean {
  if (event.key !== 'Tab') return false;
  const order = focusables(root);
  if (order.length === 0) {
    event.preventDefault();
    return true;
  }
  const at = order.indexOf(document.activeElement as HTMLElement);
  const next = event.shiftKey ? (at <= 0 ? order.length - 1 : at - 1) : (at === -1 || at === order.length - 1 ? 0 : at + 1);
  event.preventDefault();
  order[next]?.focus();
  return true;
}
