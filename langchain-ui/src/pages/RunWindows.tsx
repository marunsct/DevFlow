/**
 * A run's preview and workspace each in a window of its own (plan UX.2): outside the page shell, so the product or
 * the code has the whole window (a second monitor, say), under one thin bar that names the run and leads back to it.
 * Our own pages, not the preview's signed link: the link is renewed, and pointing and the toolbar keep working.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { changeRequestsOn } from '../api';
import { CommandPalette } from '../components/CommandPalette';
import { PreviewPanel } from '../components/PreviewPanel';
import { WorkspaceShell } from '../components/workspace/WorkspaceShell';
import { ThemeToggle } from '../components/ThemeToggle';
import { useRunPulse } from '../lib/useRunPulse';
import type { RunStatusResponse } from '../types';

const WindowBar: React.FC<{ runId: string; run: RunStatusResponse | null; what: string; view: string; problem: string | null }> = ({
  runId, run, what, view, problem,
}) => {
  const name = run?.run_name || runId.slice(0, 12);
  useEffect(() => {
    document.title = `${what} · ${name} · DevFlow.ai`;
    return () => { document.title = 'DevFlow.ai'; };
  }, [what, name]);
  return (
    <div className="flex h-10 shrink-0 items-center gap-3 border-b border-border bg-surface px-3">
      <Link to={`/runs/${runId}?view=${view}`} className="inline-flex items-center gap-1.5 text-[13px] text-text-secondary hover:text-text-primary">
        <ArrowLeft size={14} aria-hidden="true" /> Back to the run
      </Link>
      <span aria-hidden="true" className="h-4 w-px bg-border" />
      <h1 className="min-w-0 truncate text-[13px] font-semibold text-text-primary">
        {what} <span className="font-normal text-text-secondary">of {name}</span>
      </h1>
      {problem && <span role="status" className="text-[12px] text-warning">{problem}</span>}
      <span className="ml-auto flex items-center gap-1">
        <CommandPalette />
        <ThemeToggle />
      </span>
    </div>
  );
};

export const RunPreviewWindow: React.FC = () => {
  const { runId = '' } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { run, problem } = useRunPulse(runId);
  const [changesAllowed, setChangesAllowed] = useState(false);
  useEffect(() => {
    let current = true;
    void changeRequestsOn().then((on) => { if (current) setChangesAllowed(on === true); });
    return () => { current = false; };
  }, []);
  return (
    <div className="flex h-dvh flex-col bg-canvas">
      <WindowBar runId={runId} run={run} what="Preview" view="preview" problem={problem} />
      <div className="min-h-0 flex-1">
        <PreviewPanel runId={runId} runStatus={run?.status} changesAllowed={changesAllowed}
          onChangeRequest={(brief) => navigate(`/?changeOf=${runId}`, { state: { brief } })} />
      </div>
    </div>
  );
};

export const RunWorkspaceWindow: React.FC = () => {
  const { runId = '' } = useParams<{ runId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { run, problem, logs } = useRunPulse(runId, true);
  const [initialFile] = useState(() => searchParams.get('file'));
  // The file shown stays in the address, so a reload or a shared link opens it again.
  const keepInAddress = useCallback((path: string | null) => {
    setSearchParams((before) => {
      const next = new URLSearchParams(before);
      if (path) next.set('file', path); else next.delete('file');
      return next;
    }, { replace: true });
  }, [setSearchParams]);
  return (
    <div className="flex h-dvh flex-col bg-canvas">
      <WindowBar runId={runId} run={run} what="Workspace" view="workspace" problem={problem} />
      <div className="min-h-0 flex-1">
        <WorkspaceShell runId={runId} run={run} logs={logs} initialFile={initialFile} onActiveFile={keepInAddress} />
      </div>
    </div>
  );
};
