import React from 'react';
import type { RunStage, RunStatusResponse } from '../types';
import { CheckCircle2, XCircle, AlertCircle, PlayCircle, Loader2 } from 'lucide-react';

interface DynamicWorkflowUIProps {
  run: RunStatusResponse;
}

export const DynamicWorkflowUI: React.FC<DynamicWorkflowUIProps> = ({ run }) => {
  const stages = run.stages || [];
  const currentStage = run.current_stage;
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(run.status);

  // We want to combine the history (stages) with the current stage (if it's not in the history yet)
  const renderStage = (stage: RunStage, index: number, isLast: boolean) => {
    let Icon = CheckCircle2;
    let iconClass = "text-success";
    let borderClass = "border-success/30";
    let bgClass = "bg-success/5";

    if (stage.status === 'running') {
      Icon = Loader2;
      iconClass = "text-primary animate-spin";
      borderClass = "border-primary/50";
      bgClass = "bg-primary/10";
    } else if (stage.status === 'failed' || stage.status === 'error') {
      Icon = XCircle;
      iconClass = "text-danger";
      borderClass = "border-danger/50";
      bgClass = "bg-danger/10";
    } else if (stage.status === 'paused' || stage.status === 'waiting_for_approval' || stage.status === 'waiting_for_review') {
      Icon = AlertCircle;
      iconClass = "text-warning";
      borderClass = "border-warning/50";
      bgClass = "bg-warning/10";
    } else if (stage.name === currentStage && !isTerminal) {
      Icon = Loader2;
      iconClass = "text-primary animate-spin";
      borderClass = "border-primary/50";
      bgClass = "bg-primary/10";
    }

    const isCurrent = stage.name === currentStage && !isTerminal;

    return (
      <div key={`${stage.name}-${index}`} className="flex relative">
        {/* Connecting line */}
        {!isLast && (
          <div className="absolute left-6 top-10 bottom-[-1.5rem] w-px bg-border/50" />
        )}
        
        <div className="flex-none mr-4 mt-2">
          <div className={`w-12 h-12 rounded-full flex items-center justify-center border-2 ${borderClass} ${bgClass} ${isCurrent ? 'ring-4 ring-primary/20 animate-pulse' : ''}`}>
            <Icon className={`w-5 h-5 ${iconClass}`} />
          </div>
        </div>

        <div className="flex-grow py-2 pb-6">
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2">
            <div>
              <h4 className="text-sm font-bold text-white capitalize tracking-wide">{stage.name.replace(/_/g, ' ')}</h4>
              <p className="text-xs text-text-muted mt-1 font-medium">{stage.meaning}</p>
            </div>
            
            <div className="flex flex-col items-end text-xs text-text-muted">
              {stage.duration_seconds !== null && (
                <span className="font-mono bg-surface/50 px-2 py-1 rounded border border-border/30">
                  {stage.duration_seconds.toFixed(1)}s
                </span>
              )}
              {/* An approval is the step working, not repeating. These were one
                  number, and it reported a run with two retries as sixty-six. */}
              {stage.approval_count > 0 && (
                <span className="mt-1 font-mono bg-surface/50 px-2 py-0.5 rounded border border-border/30">
                  {stage.approval_count} approved
                </span>
              )}
              {stage.retry_count > 0 && (
                <span className="text-warning mt-1 font-medium bg-warning/10 px-2 py-0.5 rounded">
                  Started over: {stage.retry_count}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  // If there are no stages but we have a current_stage, mock one up
  const displayStages = [...stages];
  if (currentStage && !stages.find(s => s.name === currentStage)) {
    displayStages.push({
      name: currentStage,
      meaning: run.stage_meaning || 'Processing...',
      started_at: null,
      ended_at: null,
      status: run.status,
      duration_seconds: null,
      retry_count: 0,
      approval_count: 0,
      sprint: 0
    });
  }

  return (
    <div className="p-6 rounded-2xl glass-card border border-border/30 mb-6">
      <h3 className="text-sm font-semibold text-white mb-6 uppercase tracking-wider flex items-center gap-2">
        <PlayCircle className="w-4 h-4 text-primary" />
        Execution Workflow
      </h3>
      
      {displayStages.length === 0 ? (
        <div className="text-center py-8 text-text-muted text-sm">
          No workflow stages have been executed yet.
        </div>
      ) : (
        <div className="flex flex-col">
          {displayStages.map((stage, index) => renderStage(stage, index, index === displayStages.length - 1))}
        </div>
      )}
    </div>
  );
};
