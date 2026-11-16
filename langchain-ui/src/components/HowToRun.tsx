import { useEffect, useState } from 'react';
import { getHowToRun } from '../api';

/** The commands that install, test and start a finished product (LR.30a), from the stack it was built on. */
export function HowToRun({ runId }: { runId: string }) {
  const [steps, setSteps] = useState<string[] | null>(null);
  useEffect(() => {
    let live = true;
    getHowToRun(runId).then((found) => live && setSteps(found)).catch(() => live && setSteps([]));
    return () => { live = false; };
  }, [runId]);
  if (!steps || steps.length === 0) return null;
  return (
    <div className="mt-3 rounded-xl border border-border bg-surface/50 px-3 py-2" data-testid="how-to-run">
      <p className="text-xs font-semibold text-text-primary">How to run it</p>
      <p className="text-xs text-text-secondary">From the downloaded product's folder:</p>
      <pre className="mt-1 overflow-x-auto text-xs text-text-primary"><code>{steps.join('\n')}</code></pre>
    </div>
  );
}
