import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { aRun } from '../test/runs';
import { notificationsWanted, tell, wantNotifications } from './notify';

const waiting = aRun('run-1', 'waiting_for_approval');

let shown: { title: string; body?: string }[];
let requestPermission: ReturnType<typeof vi.fn>;

beforeEach(() => {
  shown = [];
  requestPermission = vi.fn(async () => 'granted');
  class FakeNotification {
    static permission = 'default';
    static requestPermission = requestPermission;
    onclick: (() => void) | null = null;
    constructor(title: string, options?: { body?: string }) {
      shown.push({ title, body: options?.body });
    }
    close() {}
  }
  vi.stubGlobal('Notification', FakeNotification);
});

afterEach(() => vi.unstubAllGlobals());

describe('browser notifications', () => {
  it('are off, and never asked for, until the owner turns them on', () => {
    expect(notificationsWanted()).toBe(false);
    tell(waiting, () => undefined);
    expect(requestPermission).not.toHaveBeenCalled();
    expect(shown).toEqual([]);
  });

  it('ask the browser when turned on, then tell a waiting run with its line', async () => {
    expect(await wantNotifications(true)).toBe(true);
    expect(requestPermission).toHaveBeenCalledTimes(1);

    (Notification as unknown as { permission: string }).permission = 'granted';
    tell(waiting, () => undefined);

    expect(shown).toEqual([{ title: 'A run waits for your approval', body: expect.stringContaining('Release Review') }]);
  });

  it('stay quiet once turned off, whatever the browser allows', async () => {
    (Notification as unknown as { permission: string }).permission = 'granted';
    await wantNotifications(false);
    tell(waiting, () => undefined);
    expect(shown).toEqual([]);
  });
});
