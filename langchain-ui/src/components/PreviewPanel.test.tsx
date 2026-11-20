import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PreviewPanel } from './PreviewPanel';
import type { PreviewStatus } from '../types';

const api = vi.hoisted(() => ({
  getPreview: vi.fn(),
  startPreview: vi.fn(),
  stopPreview: vi.fn(),
  sendPreviewRequest: vi.fn(),
}));
vi.mock('../api', () => api);

const LINK = '/api/runs/r/preview/app/1700000000.abc.sig/';
const status = (over: Partial<PreviewStatus>): PreviewStatus => ({
  enabled: true, state: 'none', source: null, label: null, started_at: null, reason: null, error: null,
  has_page: null, command: null, idle_minutes: 15, separate_origin: false, url: null, expires_at: null, ...over,
});
const ready = (over: Partial<PreviewStatus> = {}) => status({
  state: 'ready', source: 'accepted', label: 'sprint 2', url: LINK, expires_at: Math.floor(Date.now() / 1000) + 1800,
  has_page: true, ...over,
});

beforeEach(() => {
  api.getPreview.mockResolvedValue(status({}));
});
afterEach(() => vi.clearAllMocks());

describe('the preview tab', () => {
  it('starts the last accepted sprint or the workspace being built', async () => {
    api.startPreview.mockResolvedValue(status({ state: 'starting', source: 'live', label: 'being built' }));
    render(<PreviewPanel runId="r" />);

    await userEvent.click(await screen.findByRole('button', { name: 'Start the workspace as it is being built' }));

    expect(api.startPreview).toHaveBeenCalledWith('r', 'live');
    expect(screen.getByRole('status').textContent).toContain('Starting being built');
    expect(screen.getByRole('button', { name: 'Stop the preview' })).toBeTruthy();
  });

  it("shows a ready page in a frame that never gets the app's origin", async () => {
    api.getPreview.mockResolvedValue(ready());
    render(<PreviewPanel runId="r" />);

    const frame = await screen.findByTitle('The product');

    expect(frame.getAttribute('src')).toBe(LINK);
    expect(frame.getAttribute('sandbox')).toContain('allow-scripts');
    expect(frame.getAttribute('sandbox')).not.toContain('allow-same-origin');
  });

  it('lets a preview on its own origin keep its own storage', async () => {
    api.getPreview.mockResolvedValue(ready({ separate_origin: true, url: 'https://preview.example' + LINK }));
    render(<PreviewPanel runId="r" />);

    expect((await screen.findByTitle('The product')).getAttribute('sandbox')).toContain('allow-same-origin');
  });

  it('gives a service without a page the request console, which sends through the link', async () => {
    api.getPreview.mockResolvedValue(ready({ has_page: false }));
    api.sendPreviewRequest.mockResolvedValue({ status: 201, contentType: 'application/json', body: '{"id": 1}' });
    render(<PreviewPanel runId="r" />);

    await screen.findByRole('form', { name: 'Send a request to the preview' });
    expect(screen.queryByTitle('The product')).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText('Method'), 'POST');
    await userEvent.clear(screen.getByLabelText('Path'));
    await userEvent.type(screen.getByLabelText('Path'), '/items');
    await userEvent.type(screen.getByLabelText('JSON body'), '{{"name": "a"}');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(api.sendPreviewRequest).toHaveBeenCalledWith(LINK, 'POST', '/items', '{"name": "a"}');
    expect((await screen.findByLabelText("The preview's answer")).textContent).toContain('{"id": 1}');
  });

  it("shows why a preview failed in the product's own words", async () => {
    api.getPreview.mockResolvedValue(status({
      state: 'failed', reason: 'the product stopped by itself with exit code 1',
      error: 'Error: SQLITE_ERROR: near "TABEL": syntax error',
    }));
    render(<PreviewPanel runId="r" />);

    expect((await screen.findByLabelText('What the product wrote')).textContent).toContain('near "TABEL"');
    expect(screen.getByRole('status').textContent).toContain('exit code 1');
    expect(screen.getByRole('button', { name: 'Start the last accepted sprint' })).toBeTruthy();
  });

  it('stops a running preview', async () => {
    api.getPreview.mockResolvedValue(ready());
    api.stopPreview.mockResolvedValue(status({ state: 'stopped', reason: 'stopped by owner' }));
    render(<PreviewPanel runId="r" />);

    await userEvent.click(await screen.findByRole('button', { name: 'Stop the preview' }));

    expect(api.stopPreview).toHaveBeenCalledWith('r');
    expect(screen.queryByTitle('The product')).toBeNull();
  });

  it('says when previews are off', async () => {
    api.getPreview.mockResolvedValue(status({ enabled: false, state: 'off' }));
    render(<PreviewPanel runId="r" />);

    expect((await screen.findByText(/Previews are off/)).textContent).toContain('PRODUCT_PREVIEW');
    expect(screen.queryByRole('button')).toBeNull();
  });
});
