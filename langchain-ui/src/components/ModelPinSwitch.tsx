import React, { useEffect, useState } from 'react';
import { setModelPin } from '../api';
import { useFeedback } from './Feedback';

interface Props {
  runId: string;
  /** Whether the run is kept on the model it last ran on. */
  pinned: boolean;
  /** The model the run last ran on, shown beside the switch. */
  model?: string | null;
  /** Its server, as host:port. */
  endpoint?: string | null;
  /** Called with the new state once the server has taken it. */
  onChanged?: (pinned: boolean) => void;
  /** A smaller switch for a table row: the text shrinks to the state and the model goes into the tooltip. */
  compact?: boolean;
}

/**
 * A toggle button that keeps one run on the model it last ran on, or lets it follow the current model settings.
 *
 * On: the run's requests keep going to its own server, whatever the settings become. Off: from the next request
 * it follows the settings. Either way it works while the run is running: a request already sent finishes where
 * it was sent. The switch moves at once and goes back if the server refuses.
 */
export const ModelPinSwitch: React.FC<Props> = ({ runId, pinned, model, endpoint, onChanged, compact }) => {
  const { notify } = useFeedback();
  const [on, setOn] = useState(pinned);
  const [busy, setBusy] = useState(false);

  // The page refreshes the run on its own: when it says something new, follow it. A change of ours that is on its
  // way is not undone by the old value the page still holds.
  useEffect(() => {
    setOn(pinned);
  }, [pinned]);

  const where = model ? `${model}${endpoint ? ` @ ${endpoint}` : ''}` : '';
  const explanation = on
    ? `This run stays on its model${where ? ` (${where})` : ''}, whatever the model settings become. Turn off to follow the current settings from the next request.`
    : `This run follows the current model settings${where ? ` (now ${where})` : ''}. Turn on to keep it on the model it last ran on.`;

  const flip = async () => {
    if (busy) return;
    const wanted = !on;
    setOn(wanted);
    setBusy(true);
    try {
      await setModelPin(runId, wanted);
      onChanged?.(wanted);
    } catch (err: any) {
      setOn(!wanted);
      notify('Failed to change the model setting: ' + (err?.response?.data?.detail || err?.message || 'unknown error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label="Keep this run on its model"
      title={explanation}
      disabled={busy}
      onClick={flip}
      className={`group inline-flex items-center gap-2 rounded-full border px-2 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 disabled:opacity-60 ${
        on
          ? 'border-primary/40 bg-primary/10 text-primary hover:bg-primary/15'
          : 'border-border bg-surface text-text-secondary hover:border-border-strong hover:bg-overlay'
      }`}
    >
      <span
        aria-hidden="true"
        className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors ${
          on ? 'bg-primary' : 'bg-border-strong'
        }`}
      >
        <span
          className={`absolute left-0.5 h-3 w-3 rounded-full bg-surface shadow transition-transform ${
            on ? 'translate-x-3' : 'translate-x-0'
          }`}
        />
      </span>
      <span>{compact ? (on ? 'Pinned' : 'Follows') : on ? 'Kept on its model' : 'Follows the settings'}</span>
      {!compact && where && <span className="text-text-muted font-normal">({where})</span>}
    </button>
  );
};
