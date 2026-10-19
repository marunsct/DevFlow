/**
 * Sprint Summary Panel
 *
 * The run's sprints as a timeline of milestones with their stats (features,
 * bugs, test cycles), from `GET /runs/{id}/sprints`: the attempts the engine
 * records and renders `docs/sprint_{N}_summary.md` from (plan BG.6). A run the
 * route has nothing for - its graph state gone - falls back to reading the
 * documents themselves.
 */

import React, { useEffect, useState } from 'react';
import { usePageVisible } from '../lib/usePageVisible';
import { fetchArtifactContent, getSprints } from '../api';
import type { SprintView } from '../types';
import {
  CheckCircle2,
  XCircle,
  Bug,
  FlaskConical,
  ListChecks,
  Rocket,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

interface SprintSummaryPanelProps {
  runId: string;
  /** How many sprints the plan has; we probe up to this number. */
  maxSprints?: number;
}

interface ParsedSprint {
  number: number;
  /** How many sprints the plan has, read from this document's own heading. */
  plannedTotal: number;
  goal: string;
  status: string;
  failureReason?: string;
  /** How many times this one sprint was attempted. More than one means a re-run. */
  attempts: number;
  planned: string[];
  features: string[];
  testCases: number | null;
  casesPassed: number;
  casesFailed: number;
  testRounds: number;
  totalBugs: number;
  fixedBugs: number;
  openBugs: number;
  defects: { status: string; description: string; owner: string }[];
  attemptHistory: string[];
}

/** One sprint as the route sends it, in the shape the panel draws. */
function fromView(view: SprintView): ParsedSprint {
  return {
    number: view.number,
    plannedTotal: view.planned_total,
    goal: view.goal,
    status: view.status,
    failureReason: view.failure_reason || undefined,
    attempts: view.attempts,
    planned: view.planned,
    features: view.features,
    testCases: view.test_cases,
    casesPassed: view.cases_passed,
    casesFailed: view.cases_failed,
    testRounds: view.test_rounds,
    totalBugs: view.total_bugs,
    fixedBugs: view.fixed_bugs,
    openBugs: view.open_bugs,
    defects: view.defects,
    attemptHistory: view.attempt_history,
  };
}

/** Parse a sprint summary markdown file into structured data. */
function parseSummary(raw: string, sprintNum: number): ParsedSprint {
  const lines = raw.split('\n');

  const getField = (prefix: string) => {
    const line = lines.find((l) => l.startsWith(prefix));
    return line ? line.replace(prefix, '').trim() : '';
  };

  const section = (heading: string) => {
    const start = lines.findIndex((l) => l.trim() === heading);
    if (start < 0) return [];
    const end = lines.findIndex((l, i) => i > start && l.startsWith('#'));
    return lines
      .slice(start + 1, end > 0 ? end : lines.length)
      .filter((l) => l.startsWith('- '))
      .map((l) => l.replace(/^- /, ''));
  };

  // "# Sprint 2 of 3 Summary" - the plan's size, stated by every sprint so the
  // count does not have to be inferred from how many documents exist. Those
  // differ exactly when a sprint is re-run, which is what made a three-sprint
  // plan look like it had grown extra sprints.
  const plannedTotal = parseInt((raw.match(/^# Sprint \d+ of (\d+)/m) || [])[1] || '0', 10);
  const attempts = parseInt((getField('**Attempts:**').match(/^(\d+)/) || [])[1] || '1', 10);
  const rawCases = getField('**Test Cases:**');
  const testCases = /^\d+$/.test(rawCases) ? parseInt(rawCases, 10) : null;
  const casesPassed = parseInt(getField('- **Passed:**') || '0', 10);
  const casesFailed = parseInt(getField('- **Failed:**') || '0', 10);

  const goal = getField('**Goal:**');
  const status = getField('**Status:**');
  const failureReason = getField('**Failure Reason:**') || undefined;
  const testRounds = parseInt(getField('- **Rounds Completed:**') || '0', 10);
  const totalBugs = parseInt(getField('- **Total Bugs Found:**') || '0', 10);
  const fixedBugs = parseInt(getField('- **Bugs Fixed:**') || '0', 10);
  const openBugs = parseInt(getField('- **Bugs Open:**') || '0', 10);

  // Parse features
  const featStart = lines.findIndex((l) => l.includes('## Features Implemented'));
  const featEnd = lines.findIndex((l, i) => i > featStart && l.startsWith('##'));
  const features = lines
    .slice(featStart + 1, featEnd > 0 ? featEnd : lines.length)
    .filter((l) => l.startsWith('- '))
    .map((l) => l.replace(/^- /, ''));

  // Parse defects
  const defectStart = lines.findIndex((l) => l.includes('### Defect Summary'));
  const defects: ParsedSprint['defects'] = [];
  if (defectStart > 0) {
    for (let i = defectStart + 1; i < lines.length; i++) {
      const m = lines[i].match(/^- \[(\w+)\] (.+?) \(Owner: (.+?)\)$/);
      if (m) defects.push({ status: m[1], description: m[2], owner: m[3] });
    }
  }

  return {
    number: sprintNum, plannedTotal, goal, status, failureReason, attempts,
    planned: section('## Planned for This Sprint'), features,
    testCases, casesPassed, casesFailed,
    testRounds, totalBugs, fixedBugs, openBugs, defects,
    attemptHistory: section('## Attempt History'),
  };
}

export const SprintSummaryPanel: React.FC<SprintSummaryPanelProps> = ({ runId, maxSprints = 10 }) => {
  const [sprints, setSprints] = useState<ParsedSprint[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const visible = usePageVisible();

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setLoading(true);

    const fetchAll = async () => {
      let results: ParsedSprint[] = [];
      try {
        results = (await getSprints(runId)).sprints.map(fromView);
      } catch {
        /* an older server: read the documents */
      }
      const fromTheDocuments = results.length === 0;
      for (let i = 1; fromTheDocuments && i <= maxSprints; i++) {
        const content = await fetchArtifactContent(runId, `docs/sprint_${i}_summary.md`);
        if (content) {
          results.push(parseSummary(content, i));
        } else {
          break; // No more sprints
        }
      }
      if (!cancelled) {
        setSprints(results);
        setLoading(false);
      }
    };

    fetchAll();
    // Refresh every 30s while loading might still produce new sprints
    const interval = setInterval(fetchAll, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [runId, maxSprints, visible]);

  const toggle = (n: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  };

  if (loading && sprints.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-6 text-center">
        <p className="text-sm text-text-muted animate-pulse">Loading sprint summaries…</p>
      </div>
    );
  }

  if (sprints.length === 0) return null;

  const plannedTotal = Math.max(0, ...sprints.map((s) => s.plannedTotal));
  const reruns = sprints.filter((s) => s.attempts > 1).length;

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border/40 flex items-center gap-2">
        <Rocket className="h-4.5 w-4.5 text-primary" />
        <h2 className="text-sm font-semibold text-text-primary">Sprint Milestones</h2>
        <span className="ml-auto text-xs text-text-muted tabular-nums">
          {/* The plan's own count, so a re-run cannot read as an extra sprint. */}
          {plannedTotal > 0
            ? `${sprints.length} of ${plannedTotal} planned`
            : `${sprints.length} sprint${sprints.length !== 1 ? 's' : ''}`}
          {reruns > 0 && `  ·  ${reruns} re-run${reruns !== 1 ? 's' : ''}`}
        </span>
      </div>

      <div className="divide-y divide-border/30">
        {sprints.map((sprint) => {
          const isOpen = expanded.has(sprint.number);
          const passed = sprint.status.toLowerCase() === 'completed';
          const StatusIcon = passed ? CheckCircle2 : XCircle;
          const statusColor = passed ? 'text-success' : 'text-danger';
          const statusBg = passed ? 'bg-success-bg' : 'bg-danger-bg';

          return (
            <div key={sprint.number}>
              {/* Header row - always visible */}
              <button
                onClick={() => toggle(sprint.number)}
                className="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-overlay transition-colors"
              >
                <StatusIcon className={`h-4.5 w-4.5 flex-none ${statusColor}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-text-primary">Sprint {sprint.number}</span>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBg} ${statusColor}`}>
                      {sprint.status}
                    </span>
                    {sprint.attempts > 1 && (
                      <span
                        className="text-xs font-medium px-2 py-0.5 rounded-full bg-warning-bg text-warning"
                        title="This sprint was attempted more than once. It is one sprint, not several."
                      >
                        re-run ×{sprint.attempts}
                      </span>
                    )}
                  </div>
                  <p className="text-[12px] text-text-secondary truncate mt-0.5">{sprint.goal}</p>
                </div>

                {/* Quick stats */}
                <div className="hidden sm:flex items-center gap-4 text-xs text-text-muted tabular-nums flex-none">
                  <span className="flex items-center gap-1" title="Test cases passed / total">
                    <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">Test cases passed:</span>
                    {sprint.testCases === null ? '—' : `${sprint.casesPassed}/${sprint.testCases}`}
                  </span>
                  <span className="flex items-center gap-1" title="Bugs found">
                    <Bug className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">Bugs found:</span> {sprint.totalBugs}
                  </span>
                  <span className="flex items-center gap-1" title="Features">
                    <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">Features:</span> {sprint.features.length}
                  </span>
                </div>

                {isOpen
                  ? <ChevronDown className="h-4 w-4 text-text-muted flex-none" />
                  : <ChevronRight className="h-4 w-4 text-text-muted flex-none" />
                }
              </button>

              {/* Expanded detail */}
              {isOpen && (
                <div className="px-5 pb-4 pt-1 space-y-3 animate-fade-in">
                  {sprint.failureReason && (
                    <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2.5 text-[12px] text-danger">
                      <strong>Failure:</strong> {sprint.failureReason}
                    </div>
                  )}

                  {/* Stat cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { label: 'Test Cases', value: sprint.testCases ?? '—', icon: FlaskConical, color: 'text-primary' },
                      { label: 'Passed', value: sprint.casesPassed, icon: CheckCircle2, color: 'text-success' },
                      { label: 'Failed', value: sprint.casesFailed, icon: XCircle, color: 'text-danger' },
                      { label: 'Test Cycles', value: sprint.testRounds, icon: FlaskConical, color: 'text-primary' },
                      { label: 'Bugs Found', value: sprint.totalBugs, icon: Bug, color: 'text-warning' },
                      { label: 'Bugs Fixed', value: sprint.fixedBugs, icon: CheckCircle2, color: 'text-success' },
                      { label: 'Bugs Open', value: sprint.openBugs, icon: XCircle, color: 'text-danger' },
                    ].map((stat) => (
                      <div key={stat.label} className="rounded-lg border border-border/30 bg-overlay px-3 py-2.5 text-center">
                        <stat.icon className={`h-4 w-4 mx-auto mb-1 ${stat.color}`} />
                        <p className="text-lg font-bold text-text-primary tabular-nums">{stat.value}</p>
                        <p className="text-xs text-text-muted uppercase tracking-wider">{stat.label}</p>
                      </div>
                    ))}
                  </div>

                  {/* What the sprint plan promised - separate from what was built */}
                  {sprint.planned.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                        Planned for This Sprint
                      </h3>
                      <ul className="space-y-1">
                        {sprint.planned.map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-[12px] text-text-secondary">
                            <ListChecks className="h-3.5 w-3.5 text-primary flex-none mt-0.5" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Every attempt at this one sprint, including the failed ones */}
                  {sprint.attemptHistory.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                        Attempt History
                      </h3>
                      <ul className="space-y-1">
                        {sprint.attemptHistory.map((item, i) => (
                          <li key={i} className="text-[12px] text-text-secondary">
                            {/* Plain text: this line comes from a document an
                                agent's own output fed into, so it is never
                                inserted as markup. */}
                            {item.replace(/\*\*/g, '')}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Features */}
                  {sprint.features.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                        Features Implemented
                      </h3>
                      <ul className="space-y-1">
                        {sprint.features.map((f, i) => (
                          <li key={i} className="flex items-start gap-2 text-[12px] text-text-secondary">
                            <CheckCircle2 className="h-3.5 w-3.5 text-success flex-none mt-0.5" />
                            <span>{f}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Defects */}
                  {sprint.defects.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                        Defect Summary
                      </h3>
                      <div className="space-y-1">
                        {sprint.defects.map((d, i) => (
                          <div key={i} className="flex items-start gap-2 text-[12px]">
                            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                              d.status === 'FIXED' ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
                            }`}>
                              {d.status}
                            </span>
                            <span className="text-text-secondary flex-1">{d.description}</span>
                            <span className="text-text-muted text-xs flex-none">{d.owner}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
