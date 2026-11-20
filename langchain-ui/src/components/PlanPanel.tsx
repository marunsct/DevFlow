/**
 * Where the current sprint stands, beside the feed (plan WS.2): its work orders as done, working or open, the
 * attempt, the test round and the defects still open - from `GET /runs/{id}/plan`, read again when the run moves on.
 * Read-only.
 */
import React, { useEffect, useState } from 'react';
import { Check, Circle, Loader2 } from 'lucide-react';
import { getPlanNow } from '../api';
import type { SprintPlanNow, WorkOrderNow } from '../types';

const STATE_WORDS: Record<WorkOrderNow['state'], string> = { done: 'done', working: 'working', open: 'open' };

const StateIcon: React.FC<{ state: WorkOrderNow['state'] }> = ({ state }) =>
  state === 'done' ? (
    <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" />
  ) : state === 'working' ? (
    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" aria-hidden="true" />
  ) : (
    <Circle className="h-3 w-3 text-text-muted" aria-hidden="true" />
  );

export const PlanPanel: React.FC<{ runId: string; refreshKey: string }> = ({ runId, refreshKey }) => {
  const [plan, setPlan] = useState<SprintPlanNow | null>(null);

  useEffect(() => {
    let current = true;
    getPlanNow(runId).then((found) => current && setPlan(found)).catch(() => current && setPlan(null));
    return () => {
      current = false;
    };
  }, [runId, refreshKey]);

  if (!plan) return null;
  const orders = plan.work_orders ?? [];
  const done = orders.filter((order) => order.state === 'done').length;

  return (
    <section aria-label="The sprint's plan" className="flex min-h-0 flex-col text-[13px]" data-testid="plan-panel">
      <header className="flex-none px-3 pt-2 pb-1.5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          {plan.sprint ? `Sprint ${plan.sprint}${plan.planned_total ? ` of ${plan.planned_total}` : ''}` : 'The plan'}
        </h3>
        {plan.sprint ? (
          <>
            {plan.goal && <p className="mt-0.5 text-text-primary leading-snug">{plan.goal}</p>}
            <dl className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-text-muted tabular-nums">
              <div className="flex gap-1"><dt>Attempt</dt><dd className="text-text-secondary">{plan.attempt || 1}</dd></div>
              <div className="flex gap-1"><dt>Test round</dt><dd className="text-text-secondary">{plan.round}</dd></div>
              <div className="flex gap-1">
                <dt>Open defects</dt>
                <dd className={plan.open_defects ? 'text-danger font-medium' : 'text-text-secondary'}>{plan.open_defects}</dd>
              </div>
            </dl>
          </>
        ) : (
          <p className="mt-0.5 text-xs text-text-muted">The sprints are not planned yet.</p>
        )}
      </header>
      {orders.length > 0 && (
        <div className="min-h-0 flex-1 overflow-y-auto border-t border-border/40 px-3 py-1.5">
          <p className="mb-1 text-xs text-text-muted tabular-nums">
            Work orders: {done} of {orders.length} done
          </p>
          <ol className="space-y-1">
            {orders.map((order, index) => (
              <li key={`${index}-${order.title}`} className="flex items-start gap-2" data-state={order.state}>
                <span className="mt-0.5 grid h-4 w-4 flex-none place-items-center"><StateIcon state={order.state} /></span>
                <span className="min-w-0">
                  <span className={`block leading-snug ${order.state === 'done' ? 'text-text-muted' : 'text-text-primary'}`}>
                    {order.title}
                  </span>
                  <span className="block text-xs text-text-muted">
                    {order.role.replace(/_/g, ' ')} · <span className={order.state === 'working' ? 'text-primary' : ''}>{STATE_WORDS[order.state]}</span>
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
};
