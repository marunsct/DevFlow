import React from 'react';
import { Server } from 'lucide-react';
import type { ServerHealth } from '../types';
import { InfoRow } from '../ui';
import { describeServer, holdingTheModel } from '../lib/serverHealth';

/**
 * The build model's server as it describes itself (plan BG.5): read with one
 * request for its status, never a model call, so opening this page costs the
 * server nothing while a run is on it.
 */
export const ModelServerCard: React.FC<{ health: ServerHealth | null }> = ({ health }) => {
  const view = describeServer(health);
  const holder = holdingTheModel(health);
  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
        <Server className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 className="font-semibold text-text-primary">Model server</h2>
      </div>
      <div className="px-6 py-3">
        <p className="text-sm text-text-secondary">{view.said}</p>
        {health && !health.hosted && health.answered && (
          <dl className="mt-2">
            <InfoRow label="Model" value={health.model || '-'} />
            <InfoRow label="Quantisation" value={health.quantisation || '-'} />
            <InfoRow label="Requests at once" value={health.slots ?? '-'} />
            <InfoRow label="Context per request" value={health.slot_context ? health.slot_context.toLocaleString() : '-'} />
            <InfoRow label="Runs on it now" value={health.busy_runs.length ? health.busy_runs.join(', ') : 'none'} />
            <InfoRow label="Read at" value={new Date(health.checked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />
          </dl>
        )}
        {holder && (
          <p className="mt-2 text-xs text-warning">
            It serves one request at a time and {holder} holds it: a run started now waits for it.
          </p>
        )}
      </div>
    </div>
  );
};
