/**
 * Point and say (plan WS.5): what the preview's picker sends the run page when a person points at a part of the
 * product's page. The message comes from the product's frame, where the product's own script runs too, so it is
 * untrusted: only an exact shape with capped sizes is taken, and anything else is ignored.
 */

/** The `source` the picker's messages carry (`app.server.preview.PICKER_SCRIPT`). */
export const PICKER_SOURCE = 'devflow-preview-pick';

export interface PickedBox { x: number; y: number; width: number; height: number }

export interface PickedElement {
  /** A short CSS selector: the element's id, its test id, else a path of positions. */
  selector: string;
  tag: string;
  /** Its visible text, trimmed. */
  text: string;
  /** Its markup, cut short. */
  html: string;
  box: PickedBox;
}

const MOST_SELECTOR = 300;
const MOST_TEXT = 200;
const MOST_HTML = 1000;
const TAG = /^[a-z][a-z0-9-]{0,40}$/;

const isPlain = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
  && Object.getPrototypeOf(value) === Object.prototype;

const aString = (value: unknown, most: number, least = 0): value is string =>
  typeof value === 'string' && value.length >= least && value.length <= most;

const aNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 100_000;

const boxOf = (value: unknown): PickedBox | null => {
  if (!isPlain(value)) return null;
  const { x, y, width, height } = value;
  if (![x, y, width, height].every(aNumber) || (width as number) < 0 || (height as number) < 0) return null;
  return { x: Math.round(x as number), y: Math.round(y as number), width: Math.round(width as number), height: Math.round(height as number) };
};

/** The pointed-at element a picker's message carries, or null for anything that is not exactly one. */
export const pickedFrom = (data: unknown): PickedElement | null => {
  if (!isPlain(data) || data.source !== PICKER_SOURCE || data.version !== 1 || !isPlain(data.element)) return null;
  const { selector, tag, text, html, box } = data.element;
  if (!aString(selector, MOST_SELECTOR, 1) || !aString(tag, 41) || !TAG.test(tag)) return null;
  if (!aString(text, MOST_TEXT) || !aString(html, MOST_HTML)) return null;
  const where = boxOf(box);
  if (!where) return null;
  return { selector, tag, text, html, box: where };
};
