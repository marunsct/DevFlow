import React from 'react';

const lineStyle = (line: string): string => {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-text-muted';
  if (line.startsWith('+')) return 'text-success bg-success-bg';
  if (line.startsWith('-')) return 'text-danger bg-danger-bg';
  if (line.startsWith('@@')) return 'text-primary';
  if (line.startsWith('diff --git')) return 'text-text-secondary font-semibold mt-3';
  return 'text-text-secondary';
};

/** A unified diff, one coloured line per line, from the token pairs every theme defines. */
export const DiffText: React.FC<{ text: string; truncated?: boolean }> = ({ text, truncated }) => (
  <pre className="p-3 text-[12px] leading-5 font-mono">
    {text.split('\n').map((line, i) => (
      <div key={i} className={`whitespace-pre px-1 ${lineStyle(line)}`}>{line || ' '}</div>
    ))}
    {truncated && <div className="mt-2 text-text-muted">The rest of this change is too long to show here.</div>}
  </pre>
);
