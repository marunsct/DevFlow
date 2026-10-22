import { describe, expect, it } from 'vitest';
import { showCountInTab } from './tabBadge';

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('the count on the browser tab', () => {
  it('goes in front of the title, survives a page setting its own, and goes at zero', async () => {
    document.title = 'DevFlow.ai';
    showCountInTab(2);
    expect(document.title).toBe('(2) DevFlow.ai');

    document.title = 'run-1 · DevFlow.ai';
    await settle();
    expect(document.title).toBe('(2) run-1 · DevFlow.ai');

    showCountInTab(12);
    expect(document.title).toBe('(9+) run-1 · DevFlow.ai');

    showCountInTab(0);
    expect(document.title).toBe('run-1 · DevFlow.ai');
  });
});
