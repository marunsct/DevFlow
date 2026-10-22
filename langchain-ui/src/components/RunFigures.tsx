import React from 'react';
import type { RunStatusResponse } from '../types';
import { Progress } from '../ui';
import { ceilings, spend, tokens } from '../lib/runSummary';

const LABEL = 'text-xs text-text-muted uppercase tracking-wider';
const VALUE = 'mt-1 text-[13px] text-text-primary tabular-nums';

/**
 * How much the run has used, in the summary card (plan BG.1): its tokens, in
 * and out; its spend, priced or said not to be; and a bar for each ceiling the
 * deployment sets. Items of the card's definition list.
 */
export const RunFigures: React.FC<{ run: RunStatusResponse }> = ({ run }) => {
  const { cost } = run;
  const bars = ceilings(cost, run.max_run_tokens, run.max_run_cost_usd);
  const spent = cost ? spend(cost, run.use_frontier_model === false) : null;
  return (
    <>
      {cost && cost.total_tokens > 0 && (
        <div>
          <dt className={LABEL}>Tokens</dt>
          <dd className={VALUE} title={`${cost.successful_requests} model calls`}>
            {tokens(cost.total_tokens)}
            <span className="block text-xs text-text-muted">
              {tokens(cost.prompt_tokens)} in · {tokens(cost.completion_tokens)} out
            </span>
          </dd>
        </div>
      )}
      {/* A partial total must not read as the whole spend: the
          MAX_RUN_COST_USD ceiling counts only the calls it could price. */}
      {spent && (
        <div>
          <dt className={LABEL}>Spend</dt>
          <dd className={VALUE} title={spent.why}>
            {spent.partial ? <span className="text-warning">{spent.shown}</span> : spent.shown}
          </dd>
        </div>
      )}
      {bars.map((bar) => (
        <div key={bar.label} className="min-w-40">
          <dt className={LABEL}>Ceiling</dt>
          <dd className="mt-1.5">
            <Progress label={bar.label} value={bar.used} max={bar.limit} />
            <span className="mt-1 block text-xs text-text-muted tabular-nums">{bar.said}</span>
          </dd>
        </div>
      ))}
    </>
  );
};
