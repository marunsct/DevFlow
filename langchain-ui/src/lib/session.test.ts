import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { endSession, keepSession, refreshNow } from './session';

vi.mock('axios');

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); endSession(); vi.resetAllMocks(); });

describe('the session', () => {
  it('keeps the tokens and when the access token ends', () => {
    keepSession({ access_token: 'a1', refresh_token: 'r1', expires_in: 1800 });

    expect(localStorage.getItem('token')).toBe('a1');
    expect(localStorage.getItem('refreshToken')).toBe('r1');
    expect(Number(localStorage.getItem('tokenExpiresAt'))).toBeGreaterThan(Date.now());
  });

  it('renews five minutes before the token ends', async () => {
    vi.mocked(axios.post).mockResolvedValue({ data: { access_token: 'a2', refresh_token: 'r2', expires_in: 1800 } });
    keepSession({ access_token: 'a1', refresh_token: 'r1', expires_in: 1800 });

    await vi.advanceTimersByTimeAsync((1800 - 5 * 60) * 1000 + 100);

    expect(axios.post).toHaveBeenCalledWith('/api/auth/refresh', { refresh_token: 'r1' });
    expect(localStorage.getItem('token')).toBe('a2');
  });

  it('cannot renew without a refresh token, or when the server refuses', async () => {
    expect(await refreshNow()).toBe(false);

    localStorage.setItem('refreshToken', 'bad');
    vi.mocked(axios.post).mockRejectedValue(new Error('401'));
    expect(await refreshNow()).toBe(false);
  });

  it('forgets everything when the owner signs out', () => {
    keepSession({ access_token: 'a1', refresh_token: 'r1', expires_in: 60 });
    endSession();

    expect(['token', 'refreshToken', 'tokenExpiresAt'].map((k) => localStorage.getItem(k))).toEqual([null, null, null]);
  });
});
