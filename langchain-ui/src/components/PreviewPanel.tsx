/**
 * Try it (plan WS.4): start the product from the last accepted sprint or from the workspace as it is being built,
 * see it start, use it in a sandboxed frame - or, for a service without a page, send it requests - and stop it.
 *
 * The frame is sandboxed without `allow-same-origin` when the preview is served from the app's own host, so the
 * product's script never runs with the app's origin, where the sign-in is kept; the server says the same in the
 * page's own Content-Security-Policy. A separate preview origin may keep its own storage.
 *
 * Point and say (plan WS.5): while a person points at the page, the frame opens the link signed for pointing, whose
 * pages carry the server's picker; the element they choose arrives as a message, taken only from this frame's own
 * window and only in its exact shape (`pickedFrom`), and fills the form beside the page.
 *
 * Following the build (plan UX.11): the status names the commit the preview runs; a ready preview is looked at again
 * every `FOLLOW_MS`, keeping its link (`keepTheLink`), and when a newer version is ready one action restarts the
 * preview with it, from the same source.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getPreview, sendPreviewRequest, startPreview, stopPreview, type PreviewAnswer } from '../api';
import type { PreviewStatus } from '../types';
import { pickedFrom, type PickedElement } from '../lib/pickedElement';
import { PointAndSay } from './PointAndSay';
import { Crosshair, ShieldAlert, Square } from 'lucide-react';
import { frameBox, PreviewToolbar, ToolbarDivider, type FrameSize } from './PreviewToolbar';
import { underLink } from '../lib/previewPath';
import { FOLLOW_MS, keepTheLink } from '../lib/previewFollow';

type Preview = PreviewStatus;

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

export const PreviewPanel: React.FC<{
  runId: string;
  runStatus?: string;
  /** Whether a finished product may be changed by a change request (`PREMIUM_CHANGE_REQUESTS`). */
  changesAllowed?: boolean;
  onChangeRequest?: (brief: string) => void;
  /** More of the toolbar's right end: "Fill the window", "Open in its own window". */
  toolbarEnd?: React.ReactNode;
}> = ({ runId, runStatus, changesAllowed, onChangeRequest, toolbarEnd }) => {
  const [preview, setPreview] = useState<Preview | null>(null);
  // Plan UX.3: the page opened under the signed link, its loads (a reload is one more) and the frame's size.
  const [path, setPath] = useState('');
  const [pathProblem, setPathProblem] = useState<string | null>(null);
  const [loads, setLoads] = useState(0);
  const [size, setSize] = useState<FrameSize>({ device: 'fill', width: 0, height: 0, turned: false });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<'page' | 'requests' | null>(null);
  const [pointing, setPointing] = useState(false);
  const [picked, setPicked] = useState<PickedElement | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);

  // The picker's message is the product page's word: only this frame's own window is heard, only while pointing.
  useEffect(() => {
    if (!pointing) return undefined;
    const heard = (event: MessageEvent) => {
      const own = frame.current?.contentWindow;
      if (!own || event.source !== own) return;
      const element = pickedFrom(event.data);
      if (element) setPicked(element);
    };
    window.addEventListener('message', heard);
    return () => window.removeEventListener('message', heard);
  }, [pointing]);

  const load = useCallback(async () => {
    try {
      const found = await getPreview(runId);
      setPreview((previous) => keepTheLink(previous, found));
    } catch (error) {
      setProblem(detailOf(error));
    }
  }, [runId]);

  useEffect(() => { void load(); }, [load]);

  // A starting preview is looked at until it is ready or has failed; a ready one is looked at again to follow the
  // build, and its link is renewed before it expires.
  useEffect(() => {
    if (preview?.state === 'starting') {
      const timer = setTimeout(() => void load(), POLL_MS);
      return () => clearTimeout(timer);
    }
    if (preview?.state === 'ready' && preview.expires_at) {
      const renewal = Math.max(5_000, preview.expires_at * 1000 - Date.now() - 60_000);
      const timer = setTimeout(() => void load(), Math.min(FOLLOW_MS, renewal));
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
  const ready = preview.state === 'ready' && !!preview.url;
  const canPoint = ready && shown === 'page' && !!preview.pick_url;
  const base = (pointing && preview.pick_url) || preview.url || '';
  const framed = base ? underLink(base, path) ?? base : undefined;
  const box = frameBox(size);
  const go = (typed: string) => {
    if (!base) return;
    if (underLink(base, typed) === null) {
      setPathProblem('Only a path inside this preview can be opened, such as /items/7.');
      return;
    }
    setPathProblem(null);
    setPath(typed.trim());
    setLoads((n) => n + 1);
  };
  const pill = 'inline-flex h-7 items-center rounded-md px-2.5 text-[13px] font-medium transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]';

  const start = (
    <>
      {!active && (
        <>
          <button type="button" disabled={busy} onClick={() => act(() => startPreview(runId, 'accepted'))}
            className={`${pill} bg-primary text-primary-foreground`}>
            Start the last accepted sprint
          </button>
          <button type="button" disabled={busy} onClick={() => act(() => startPreview(runId, 'live'))}
            className={`${pill} border border-border text-text-primary hover:bg-overlay`}>
            Start the workspace as it is being built
          </button>
        </>
      )}
      {active && (
        <button type="button" disabled={busy} onClick={() => act(() => stopPreview(runId))}
          title={`Stops by itself after ${preview.idle_minutes} minutes without a request`}
          className={`${pill} gap-1.5 border border-border text-text-primary hover:bg-overlay`}>
          <Square size={11} aria-hidden="true" className="fill-current" /> Stop the preview
        </button>
      )}
    </>
  );
  const end = (
    <>
      {ready && preview.has_page !== false && (
        <>
          <ToolbarDivider />
          <div role="tablist" aria-label="How the preview is shown" className="flex items-center gap-0.5 text-[13px]">
            {(['page', 'requests'] as const).map((choice) => (
              <button key={choice} type="button" role="tab" aria-selected={shown === choice} onClick={() => setView(choice)}
                className={`h-7 rounded-md px-2 ${shown === choice ? 'bg-overlay-strong text-text-primary' : 'text-text-secondary hover:text-text-primary'}`}>
                {choice === 'page' ? 'Page' : 'Requests'}
              </button>
            ))}
          </div>
        </>
      )}
      {canPoint && (
        <button type="button" aria-pressed={pointing} onClick={() => setPointing(!pointing)}
          className={`${pill} ml-1 gap-1.5 border ${pointing ? 'border-accent bg-accent-soft text-text-primary' : 'border-border text-text-secondary hover:text-text-primary'}`}>
          <Crosshair size={13} aria-hidden="true" />
          {pointing ? 'Stop pointing' : 'Point at a part of the page'}
        </button>
      )}
      <p role="status" className="ml-auto min-w-0 truncate pl-2 text-[13px] text-text-secondary">
        {preview.state === 'none' && 'No preview yet.'}
        {preview.state === 'starting' && `Starting ${preview.label ?? 'the product'}…`}
        {preview.state === 'ready' && <>Showing {preview.label}{preview.commit && <span className="ml-1 font-mono text-[12px] text-text-muted" title={`Commit ${preview.commit}`}>· {preview.commit.slice(0, 7)}</span>}{preview.source === 'live' && <span className="ml-1 text-warning">(being built: it may change or break)</span>}</>}
        {preview.state === 'failed' && `The preview failed: ${preview.reason ?? 'the product did not start'}.`}
        {preview.state === 'stopped' && `The preview stopped: ${preview.reason ?? 'stopped'}.`}
      </p>
      {active && preview.behind && (
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-accent bg-accent-soft px-2 py-0.5 text-[12px] text-text-primary">
          <span role="note">A newer version is ready{preview.newer ? `: ${preview.newer}` : ''}.</span>
          <button type="button" disabled={busy}
            onClick={() => act(() => startPreview(runId, preview.source ?? 'accepted', true))}
            className="font-medium underline underline-offset-2 hover:no-underline disabled:opacity-50">
            Restart with it
          </button>
        </span>
      )}
      {/* Plan UX.4: on the app's own host the frame has no origin of its own, so the product cannot keep anything. */}
      {ready && !preview.separate_origin && (
        <span
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-warning/40 bg-warning-bg px-2 py-0.5 text-[12px] text-warning"
          title="This preview is served from the app's own address, so the product's page runs without an origin of its own: browser storage and cookies are refused. An administrator can give previews their own address (PRODUCT_PREVIEW_ORIGIN)."
        >
          <ShieldAlert size={12} aria-hidden="true" /> Storage and sign-in do not work in this preview
        </span>
      )}
      {toolbarEnd}
    </>
  );

  return (
    <section aria-label="Preview" className="flex h-full min-h-0 flex-col">
      <PreviewToolbar start={start} end={end} framed={ready && shown === 'page'} path={path} onGo={go}
        onReload={() => setLoads((n) => n + 1)} size={size} onSize={setSize} />
      {(problem || pathProblem) && <p role="alert" className="px-3 pt-2 text-sm text-danger">{problem ?? pathProblem}</p>}
      {pointing && canPoint && <p className="px-3 pt-2 text-[13px] text-text-muted">Choose a part of the page, then say what should change there.</p>}
      {preview.state === 'failed' && preview.error && (
        <pre aria-label="What the product wrote" className="m-3 max-h-80 overflow-auto rounded-lg bg-overlay p-3 text-[12px] font-mono text-text-secondary whitespace-pre-wrap">{preview.error}</pre>
      )}
      {ready && (
        shown === 'page' ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
            <div className={`min-h-0 min-w-0 flex-1 ${box ? 'overflow-auto bg-inset p-4' : 'flex'}`}>
              <iframe
                key={loads}
                ref={frame}
                title="The product"
                src={framed}
                sandbox={preview.separate_origin ? `${SANDBOX} allow-same-origin` : SANDBOX}
                referrerPolicy="no-referrer"
                style={box ? { width: `${box.width}px`, height: `${box.height}px` } : undefined}
                className={box
                  ? 'mx-auto block shrink-0 rounded-[10px] border border-border-strong bg-surface shadow-[var(--shadow-2)]'
                  : 'min-h-80 w-full flex-1 bg-surface'}
              />
            </div>
            {picked && (
              <div className="p-3 lg:w-96 lg:shrink-0 lg:pl-0">
                <PointAndSay runId={runId} element={picked} runStatus={runStatus} changesAllowed={changesAllowed}
                  onChangeRequest={onChangeRequest} onDone={() => setPicked(null)} />
              </div>
            )}
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto p-3">
            <RequestConsole link={preview.url!} />
          </div>
        )
      )}
    </section>
  );
};
