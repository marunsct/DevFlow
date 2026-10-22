/**
 * The signed-in session: the access token, the refresh token and when the
 * access token ends. The token is renewed five minutes before it ends, so a
 * run watched for hours is never interrupted by a reload to the sign-in page.
 */
import axios from 'axios';

const REFRESH_BEFORE_MS = 5 * 60 * 1000;
let timer: ReturnType<typeof setTimeout> | null = null;

interface TokenAnswer {
  access_token: string;
  refresh_token?: string | null;
  expires_in?: number | null;
}

/** Keep a sign-in's tokens and arrange the renewal. */
export function keepSession(answer: TokenAnswer): void {
  localStorage.setItem('token', answer.access_token);
  if (answer.refresh_token) localStorage.setItem('refreshToken', answer.refresh_token);
  if (answer.expires_in) localStorage.setItem('tokenExpiresAt', String(Date.now() + answer.expires_in * 1000));
  scheduleRefresh();
}

export function endSession(): void {
  for (const key of ['token', 'refreshToken', 'tokenExpiresAt']) localStorage.removeItem(key);
  if (timer) clearTimeout(timer);
  timer = null;
}

/** Ask for a new access token with the refresh token; false when it cannot be had. */
export async function refreshNow(): Promise<boolean> {
  const refresh = localStorage.getItem('refreshToken');
  if (!refresh) return false;
  try {
    const { data } = await axios.post<TokenAnswer>('/api/auth/refresh', { refresh_token: refresh });
    keepSession(data);
    return true;
  } catch {
    return false;
  }
}

/** Renew shortly before the token ends (or at once if it already is about to). */
export function scheduleRefresh(): void {
  if (timer) clearTimeout(timer);
  const ends = Number(localStorage.getItem('tokenExpiresAt') || 0);
  if (!ends || !localStorage.getItem('refreshToken')) return;
  timer = setTimeout(() => { void refreshNow(); }, Math.max(5_000, ends - Date.now() - REFRESH_BEFORE_MS));
}
