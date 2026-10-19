import React, { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bell, X } from 'lucide-react';
import type { RunSummary } from '../types';
import { Button, Checkbox, IconButton, useFeedback } from '../ui';
import { approveInOneTap } from '../lib/commands';
import { inboxLine, inboxParts, oneTapAnswer } from '../lib/needsYou';
import { browserCanNotify, notificationsWanted, wantNotifications } from '../lib/notify';
import { useNeedsYou } from '../lib/useNeedsYou';

/**
 * The header's inbox (plan BG.2): one row per run waiting for the owner, each
 * answered in one tap or opened, then the runs that stopped since the owner
 * last looked. The count is the live waiting runs only.
 */
export const NeedsYouInbox: React.FC = () => {
  const navigate = useNavigate();
  const needsYou = useNeedsYou((runId) => navigate(`/runs/${runId}`));
  const { notify } = useFeedback();
  const [open, setOpen] = useState(false);
  const [answering, setAnswering] = useState<string | null>(null);
  const [notifying, setNotifying] = useState(notificationsWanted);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      trigger.current?.focus();
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !trigger.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open]);

  const approve = async (run: RunSummary) => {
    setAnswering(run.run_id);
    try {
      await approveInOneTap(run);
      notify('Approved: the run goes on.', 'info');
      needsYou.refresh();
    } catch {
      notify('The approval did not go through; open the run to answer it there.');
    } finally {
      setAnswering(null);
    }
  };

  const toggleNotifications = async (on: boolean) => {
    const shown = await wantNotifications(on);
    setNotifying(on);
    if (on && !shown) notify('The browser does not allow notifications for this page; its site settings can.', 'info');
  };

  const { count, waiting, stopped } = needsYou;
  const summary = waitingSummary(count);

  return (
    <div className="relative">
      <button
        ref={trigger}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={summary}
        title={summary}
        onClick={() => setOpen((shown) => !shown)}
        className={
          count > 0
            ? 'flex h-9 items-center gap-1.5 rounded-full border border-primary/50 bg-accent-soft px-2.5 text-xs font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]'
            : 'inline-flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary hover:bg-overlay hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]'
        }
      >
        <Bell className="h-4 w-4" aria-hidden="true" />
        {count > 0 && (
          <span aria-hidden="true">
            {count}
            <span className="hidden sm:inline"> need{count === 1 ? 's' : ''} you</span>
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panel}
          id={panelId}
          role="region"
          aria-label="What needs you"
          className="absolute right-0 z-[60] mt-2 w-[min(24rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface-raised p-3 shadow-[var(--shadow-2)]"
        >
          <InboxPanel
            waiting={waiting}
            stopped={stopped}
            answering={answering}
            onApprove={(run) => void approve(run)}
            onOpen={(runId) => { setOpen(false); navigate(`/runs/${runId}`); }}
            onLeave={() => setOpen(false)}
            onDismiss={needsYou.dismiss}
            notifying={notifying}
            onNotifying={(on) => void toggleNotifications(on)}
          />
        </div>
      )}
    </div>
  );
};

const waitingSummary = (count: number): string =>
  count === 0 ? 'Nothing waits for you' : `${count} run${count === 1 ? '' : 's'} waiting for you`;

export interface InboxPanelProps {
  waiting: RunSummary[];
  stopped: RunSummary[];
  /** The run whose approval is on its way. */
  answering: string | null;
  onApprove: (run: RunSummary) => void;
  onOpen: (runId: string) => void;
  /** A link in the panel was followed. */
  onLeave: () => void;
  onDismiss: (run: RunSummary) => void;
  notifying: boolean;
  onNotifying: (on: boolean) => void;
}

/** Which run and where on one line, cut short when narrow; what happens next on its own line, never cut. */
const RunLine: React.FC<{ run: RunSummary; onLeave: () => void }> = ({ run, onLeave }) => {
  const { who, what, timed } = inboxParts(run);
  return (
    <Link to={`/runs/${run.run_id}`} onClick={onLeave} title={inboxLine(run)} className="group min-w-0 flex-1 text-sm">
      <span className="block truncate text-text-primary group-hover:underline">{who}</span>
      <span className={timed ? 'block text-xs font-medium text-warning' : 'block text-xs text-text-secondary'}>{what}</span>
    </Link>
  );
};

/** What the inbox lists, apart from its trigger: the kit page shows it with sample runs. */
export const InboxPanel: React.FC<InboxPanelProps> = ({
  waiting, stopped, answering, onApprove, onOpen, onLeave, onDismiss, notifying, onNotifying,
}) => (
  <>
    <h2 className="px-1 text-sm font-semibold text-text-primary">{waitingSummary(waiting.length)}</h2>

    {waiting.length > 0 && (
      <ul className="mt-2 space-y-1">
        {waiting.map((run) => (
          <li key={run.run_id} className="flex items-center gap-2 rounded-lg px-1 py-1.5 hover:bg-overlay">
            <RunLine run={run} onLeave={onLeave} />
            {oneTapAnswer(run) ? (
              <Button size="sm" variant="primary" loading={answering === run.run_id} onClick={() => onApprove(run)}>
                Approve
              </Button>
            ) : (
              <Button size="sm" onClick={() => onOpen(run.run_id)}>
                Open
              </Button>
            )}
            <IconButton size="sm" label={`Hide ${run.run_id} until it moves`} icon={<X className="h-3.5 w-3.5" />} onClick={() => onDismiss(run)} />
          </li>
        ))}
      </ul>
    )}

    {stopped.length > 0 && (
      <>
        <h3 className="mt-3 px-1 text-xs font-medium text-text-muted">Stopped since you last looked</h3>
        <ul className="mt-1 space-y-1">
          {stopped.map((run) => (
            <li key={run.run_id} className="flex items-center gap-2 rounded-lg px-1 py-1.5 hover:bg-overlay">
              <RunLine run={run} onLeave={onLeave} />
              <IconButton size="sm" label={`Hide ${run.run_id}`} icon={<X className="h-3.5 w-3.5" />} onClick={() => onDismiss(run)} />
            </li>
          ))}
        </ul>
      </>
    )}

    <div className="mt-3 flex items-center justify-between gap-3 border-t border-border px-1 pt-3">
      {browserCanNotify() ? (
        <Checkbox
          label="Tell me in the browser"
          hint="When a run waits, stops or finishes, from any page."
          checked={notifying}
          onChange={(event) => onNotifying(event.target.checked)}
        />
      ) : (
        <span className="text-xs text-text-muted">This browser shows no notifications.</span>
      )}
      <Link to="/runs" onClick={onLeave} className="shrink-0 text-xs font-medium text-primary hover:underline">
        All runs
      </Link>
    </div>
  </>
);
