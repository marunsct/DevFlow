import React from 'react';

interface ProgressBarProps {
  progress: number; // 0 to 100
  label?: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ progress, label }) => {
  const boundedProgress = Math.max(0, Math.min(100, progress));

  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-sm font-medium text-slate-700">{label}</span>
          <span className="text-sm font-medium text-slate-500">{boundedProgress}%</span>
        </div>
      )}
      <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
        <div
          className="bg-success h-2.5 rounded-full transition-all duration-500 ease-out"
          style={{ width: `${boundedProgress}%` }}
        ></div>
      </div>
    </div>
  );
};
