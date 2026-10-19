/**
 * What the command palette offers and how a typed query picks from it. Every
 * word of the query must appear in the command's title or its keywords; a
 * title that starts with the query comes first.
 */
import { submitApproval, submitReview } from '../api';
import type { RunSummary } from '../types';
import { oneTapAnswer } from './needsYou';

export interface Command {
  id: string;
  title: string;
  /** Shown beside the title: where it goes or what it answers. */
  hint?: string;
  /** Other words it is found by. */
  keywords?: string;
  run: () => void | Promise<void>;
}

export function matchCommands(commands: Command[], query: string): Command[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return commands;
  const found = commands.filter((command) => {
    const text = `${command.title} ${command.hint ?? ''} ${command.keywords ?? ''}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
  const leading = (command: Command) => (command.title.toLowerCase().startsWith(words[0]) ? 0 : 1);
  return found.sort((a, b) => leading(a) - leading(b));
}

/** Approve a waiting gate or review as it stands, from the inbox or the palette. */
export async function approveInOneTap(run: RunSummary): Promise<void> {
  if (oneTapAnswer(run) === 'review') await submitReview(run.run_id, { action: 'approve', comment: null });
  else await submitApproval(run.run_id, { action: 'approve', reason: null });
}

/** "⌘K" on a Mac, "Ctrl K" elsewhere. */
export const paletteKeys = (): string =>
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘K' : 'Ctrl K';

/** Every key the interface answers to, as the shortcuts sheet lists them. */
export const SHORTCUTS: { keys: string[]; what: string }[] = [
  { keys: [paletteKeys()], what: 'Open the command palette: go to a run, start a build, approve a waiting gate' },
  { keys: ['?'], what: 'Show these shortcuts' },
  { keys: ['t'], what: 'Switch the theme' },
  { keys: ['Esc'], what: 'Close a dialog, a panel or the palette' },
  { keys: ['↑', '↓', 'Enter'], what: 'In the palette: move through the commands and run one' },
];

/** Whether a key press belongs to a field the person is typing in. */
export const typing = (target: EventTarget | null): boolean => {
  const element = target as HTMLElement | null;
  return !!element && (element.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName));
};
