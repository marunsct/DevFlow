import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, changeRequestsOn } from './index';

// Plan WS.7: the run page hides "Request a change" unless the change requests switch is on.
describe('whether change requests are on', () => {
  afterEach(() => { vi.restoreAllMocks(); });

  const switches = (on: boolean) => ({ data: [
    { name: 'PREMIUM_MODEL_TUNING', on: true },
    { name: 'PREMIUM_CHANGE_REQUESTS', on },
  ] });

  it('reads the change requests switch from the list every signed-in person sees', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(switches(true));
    expect(await changeRequestsOn()).toBe(true);
  });

  it('is off when that switch is off, or the list cannot be read', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce(switches(false)).mockRejectedValueOnce(new Error('403'));
    expect(await changeRequestsOn()).toBe(false);
    expect(await changeRequestsOn()).toBe(false);
  });
});
