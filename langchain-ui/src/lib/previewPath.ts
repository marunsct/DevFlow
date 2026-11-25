/**
 * Where a path typed in the preview's toolbar leads (plan UX.3): always under the signed link the server gave, never
 * another host, another scheme or a folder above the link. `null` when the path would leave it.
 */
export function underLink(link: string, path: string): string | null {
  const typed = path.trim();
  // A scheme ("https:", "javascript:"), a protocol-relative address or a backslash (read as a slash) leaves the link.
  if (/^[a-z][a-z0-9+.-]*:/i.test(typed) || typed.startsWith('//') || typed.includes('\\')) return null;
  const here = typeof window !== 'undefined' && window.location ? window.location.origin : 'http://localhost';
  let base: URL;
  let target: URL;
  try {
    base = new URL(link.endsWith('/') ? link : `${link}/`, here);
    target = new URL(typed.replace(/^\/+/, ''), base);
  } catch {
    return null;
  }
  // The address parser has already folded "..", "%2e%2e" and the like: what is left must still start with the link.
  if (target.origin !== base.origin || !target.pathname.startsWith(base.pathname)) return null;
  const rest = target.pathname.slice(base.pathname.length) + target.search + target.hash;
  return `${link.endsWith('/') ? link : `${link}/`}${rest}`;
}

/** A device the frame is sized as: no emulation, only a frame of that size, centred. */
export interface DeviceSize { id: 'fill' | 'phone' | 'tablet' | 'custom'; label: string; width: number; height: number }

export const DEVICE_SIZES: DeviceSize[] = [
  { id: 'fill', label: 'Fill the panel', width: 0, height: 0 },
  { id: 'phone', label: 'Phone', width: 390, height: 844 },
  { id: 'tablet', label: 'Tablet', width: 820, height: 1180 },
  { id: 'custom', label: 'Custom size', width: 1280, height: 800 },
];
