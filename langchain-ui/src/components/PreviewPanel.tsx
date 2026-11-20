/**
 * Try it (plan WS.4): start the product from the last accepted sprint or from the workspace as it is being built,
 * see it start, use it in a sandboxed frame - or, for a service without a page, send it requests - and stop it.
 *
 * The frame is sandboxed without `allow-same-origin` when the preview is served from the app's own host, so the
 * product's script never runs with the app's origin, where the sign-in is kept; the server says the same in the
 * page's own Content-Security-Policy. A separate preview origin may keep its own storage.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { getPreview, sendPreviewRequest, startPreview, stopPreview, type PreviewAnswer } from '../api';
import type { PreviewStatus } from '../types';

/** How often a starting preview is looked at again. */
export const POLL_MS = 2000;
/** The frame's sandbox on the app's own host: scripts, forms and pop-ups, never the app's origin. */
export const SANDBOX = 'allow-scripts allow-forms allow-popups allow-modals allow-downloads';

const detailOf = (error: any): string => error?.response?.data?.detail ?? 'The preview could not be reached.';

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

const RequestConsole: React.FC<{ link: string }> = ({ link }) => {
  const [method, setMethod] = useState<string>('GET');
  const [path, setPath] = useState('/');
  const [body, setBody] = useState('');
  const [answer, setAnswer] = useState<PreviewAnswer | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    setSending(true);
    setProblem(null);
    try {
      setAnswer(await sendPreviewRequest(link, method, path, body));
    } catch {
      setProblem('The request did not reach the preview.');
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={send} className="space-y-2" aria-label="Send a request to the preview">
      <div className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="preview-method">Method</label>
        <select id="preview-method" value={method} onChange={(e) => setMethod(e.target.value)}
          className="rounded-lg bg-overlay border border-border/60 px-2 py-1.5 text-sm text-text-primary">
          {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <label className="sr-only" htmlFor="preview-path">Path</label>
        <input id="preview-path" value={path} onChange={(e) => setPath(e.target.value)}
          className="min-w-0 flex-1 rounded-lg bg-overlay border border-border/60 px-3 py-1.5 font-mono text-sm text-text-primary" />
        <button type="submit" disabled={sending}
          className="shrink-0 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50">
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>
      {method !== 'GET' && (
        <>
          <label className="sr-only" htmlFor="preview-body">JSON body</label>
          <textarea id="preview-body" value={body} onChange={(e) => setBody(e.target.value)} rows={4}
            placeholder='{"name": "example"}'
            className="w-full rounded-lg bg-overlay border border-border/60 px-3 py-2 font-mono text-sm text-text-primary" />
        </>
      )}
      {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
      {answer && (
        <div aria-label="The preview's answer" className="rounded-lg border border-border/60">
          <p className="border-b border-border/60 px-3 py-1.5 text-xs text-text-secondary tabular-nums">
            {answer.status} {answer.contentType && <span className="text-text-muted">· {answer.contentType}</span>}
          </p>
          <pre className="max-h-80 overflow-auto p-3 text-[12px] font-mono text-text-secondary whitespace-pre-wrap">{answer.body.slice(0, 100_000)}</pre>
        </div>
      )}
    </form>
  );
};

export const PreviewPanel: React.FC<{ runId: string }> = ({ runId }) => {
  const [preview, setPreview] = useState<PreviewStatus | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<'page' | 'requests' | null>(null);

  const load = useCallback(async () => {
    try {
      setPreview(await getPreview(runId));
    } catch (error) {
      setProblem(detailOf(error));
    }
  }, [runId]);

  useEffect(() => { void load(); }, [load]);

  // A starting preview is looked at until it is ready or has failed; a link is renewed before it expires.
  useEffect(() => {
    if (preview?.state === 'starting') {
      const timer = setTimeout(() => void load(), POLL_MS);
      return () => clearTimeout(timer);
    }
    if (preview?.state === 'ready' && preview.expires_at) {
      const timer = setTimeout(() => void load(), Math.max(5_000, preview.expires_at * 1000 - Date.now() - 60_000));
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [preview, load]);

  const act = async (work: () => Promise<PreviewStatus>) => {
    setBusy(true);
    setProblem(null);
    try {
      setPreview(await work());
    } catch (error) {
      setProblem(detailOf(error));
    } finally {
      setBusy(false);
    }
  };

  if (!preview) {
    return <p className="p-4 text-sm text-text-muted">{problem ?? 'Loading the preview…'}</p>;
  }
  if (preview.state === 'off') {
    return (
      <p className="p-4 text-sm text-text-muted">
        Previews are off on this deployment. An administrator turns them on with the PRODUCT_PREVIEW switch.
      </p>
    );
  }

  const active = preview.state === 'starting' || preview.state === 'ready';
  const shown = view ?? (preview.has_page === false ? 'requests' : 'page');
  return (
    <section aria-label="Preview" className="flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {!active && (
          <>
            <button type="button" disabled={busy} onClick={() => act(() => startPreview(runId, 'accepted'))}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50">
              Start the last accepted sprint
            </button>
            <button type="button" disabled={busy} onClick={() => act(() => startPreview(runId, 'live'))}
              className="px-3 py-1.5 rounded-lg border border-border/60 text-sm text-text-primary disabled:opacity-50">
              Start the workspace as it is being built
            </button>
          </>
        )}
        {active && (
          <button type="button" disabled={busy} onClick={() => act(() => stopPreview(runId))}
            className="px-3 py-1.5 rounded-lg border border-border/60 text-sm text-text-primary disabled:opacity-50">
            Stop the preview
          </button>
        )}
        <p role="status" className="text-sm text-text-secondary">
          {preview.state === 'none' && 'No preview yet.'}
          {preview.state === 'starting' && `Starting ${preview.label ?? 'the product'}…`}
          {preview.state === 'ready' && <>Showing {preview.label}{preview.source === 'live' && <span className="ml-1 text-warning">(being built: it may change or break)</span>}</>}
          {preview.state === 'failed' && `The preview failed: ${preview.reason ?? 'the product did not start'}.`}
          {preview.state === 'stopped' && `The preview stopped: ${preview.reason ?? 'stopped'}.`}
        </p>
        {active && <span className="text-xs text-text-muted">Stops after {preview.idle_minutes} minutes without a request.</span>}
      </div>
      {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
      {preview.state === 'failed' && preview.error && (
        <pre aria-label="What the product wrote" className="max-h-80 overflow-auto rounded-lg bg-overlay p-3 text-[12px] font-mono text-text-secondary whitespace-pre-wrap">{preview.error}</pre>
      )}
      {preview.state === 'ready' && preview.url && (
        <>
          {preview.has_page !== false && (
            <div role="tablist" aria-label="How the preview is shown" className="flex gap-2 text-sm">
              {(['page', 'requests'] as const).map((choice) => (
                <button key={choice} type="button" role="tab" aria-selected={shown === choice} onClick={() => setView(choice)}
                  className={`px-2 py-1 rounded ${shown === choice ? 'bg-overlay-strong text-text-primary' : 'text-text-secondary'}`}>
                  {choice === 'page' ? 'Page' : 'Requests'}
                </button>
              ))}
            </div>
          )}
          {shown === 'page' ? (
            <iframe
              title="The product"
              src={preview.url}
              sandbox={preview.separate_origin ? `${SANDBOX} allow-same-origin` : SANDBOX}
              referrerPolicy="no-referrer"
              className="min-h-112 w-full flex-1 rounded-lg border border-border/60 bg-white"
            />
          ) : (
            <RequestConsole link={preview.url} />
          )}
        </>
      )}
    </section>
  );
};
