import React from 'react';

interface ProgressBarProps {
  progress: number;
  label?: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ progress, label }) => {
  const boundedProgress = Math.max(0, Math.min(100, progress));

  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">{label}</span>
          <span className="text-xs font-semibold text-primary">{boundedProgress}%</span>
        </div>
      )}
      <div className="w-full bg-surface rounded-full h-2 overflow-hidden border border-border/30">
        <div
          className="h-2 rounded-full transition-all duration-700 ease-out relative"
          style={{
            width: `${boundedProgress}%`,
            background: 'linear-gradient(90deg, #6366f1, #8b5cf6, #a78bfa)',
          }}
        >
          {boundedProgress > 0 && boundedProgress < 100 && (
            <div className="absolute right-0 top-0 h-full w-4 bg-white/30 rounded-full animate-pulse" />
          )}
        </div>
      </div>
    </div>
  );
};
