import React, { useEffect, useState } from 'react';
import { PlayCircle } from 'lucide-react';
import { Button, useFeedback } from '../ui';
import { describeRunDefaults, forgetRunDefaults, readRunDefaults, type RunDefaults } from '../lib/runDefaults';

/** The run defaults the start form opens with, and a way to forget them (plan UI-S5). */
export const RunDefaultsCard: React.FC = () => {
  const { notify } = useFeedback();
  const [defaults, setDefaults] = useState<RunDefaults | null | undefined>(undefined);

  useEffect(() => {
    let live = true;
    readRunDefaults().then((found) => live && setDefaults(found));
    return () => {
      live = false;
    };
  }, []);

  const forget = async () => {
    try {
      await forgetRunDefaults();
      setDefaults(null);
      notify('Forgotten: the start form opens with its own defaults.', 'info');
    } catch {
      notify('They could not be forgotten; try again.');
    }
  };

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
        <PlayCircle className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 className="font-semibold text-text-primary">How a run starts</h2>
      </div>
      <div className="px-6 py-4 space-y-3">
        {defaults === undefined ? null : defaults === null ? (
          <p className="text-sm text-text-secondary">
            Nothing saved yet. The choices you start a run with are kept here, and the start form opens with them.
          </p>
        ) : (
          <>
            <p className="text-sm text-text-secondary">The start form opens with the choices you last started a run with:</p>
            <ul className="space-y-1 text-sm text-text-primary">
              {describeRunDefaults(defaults).map((line) => <li key={line}>{line}</li>)}
            </ul>
            <Button size="sm" onClick={() => void forget()}>Forget them</Button>
          </>
        )}
      </div>
    </div>
  );
};
