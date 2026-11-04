import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileText, PlayCircle, FolderOpen } from 'lucide-react';
import { api, createRun, deleteRun, startRun, getFrontierStatus, getOutcomes, uploadCodebase, type FrontierStatus, type RunForecast } from '../api';
import { Link } from 'react-router-dom';
import { typicalTime } from '../lib/runSummary';
import { describeServer, holdingTheModel, useServerHealth } from '../lib/serverHealth';
import { CriteriaPreview } from '../components/CriteriaPreview';
import { Button, Checkbox, Input, Textarea } from '../ui';

const DRAFT = 'devflow.briefDraft';
const readDraft = (): string => {
  try {
    return localStorage.getItem(DRAFT) ?? '';
  } catch {
    return '';
  }
};
const keepDraft = (text: string): void => {
  try {
    if (text) localStorage.setItem(DRAFT, text);
    else localStorage.removeItem(DRAFT);
  } catch {
    /* the draft lives in this page only */
  }
};
import { readRunDefaults, saveRunDefaults } from '../lib/runDefaults';

// How much the run stops for the person who started it: three answers to one
// question, each exactly the settings the form has always sent.
type Involvement = 'hands_off' | 'review_stages' | 'every_step';
const INVOLVEMENT: { id: Involvement; title: string; text: string }[] = [
  { id: 'hands_off', title: 'Hands-off', text: 'Nothing stops for you. The run comes back when the product is done or something fails.' },
  { id: 'review_stages', title: 'Review the key stages', text: 'Every file write and tool call goes ahead; the run stops at the reviews you keep below.' },
  { id: 'every_step', title: 'Approve every step', text: 'The reviews below, and each file write and tool call asked before it runs.' },
];

const GATES = [
  ['reviewIntake', 'Product intake', 'What the brief asks for, read back before anything is designed.'],
  ['reviewTechSpec', 'Technical specification', 'The design the build follows.'],
  ['reviewAcceptance', 'Acceptance tests', 'The tests that decide when the product is done, before they are locked.'],
  ['reviewSprint', 'End of each sprint', 'With the criteria that pass, screenshots and decisions. A requested change becomes a tracked change request.'],
  ['reviewRelease', 'Release', 'The finished product, once every acceptance criterion passes.'],
  ['reviewEscalation', 'When work is stuck', 'You decide to go on or try again with your guidance. Off, the run decides and records why.'],
] as const;

const Step: React.FC<{ n: number; title: string; aside?: React.ReactNode; children: React.ReactNode }> = ({ n, title, aside, children }) => (
  <section aria-labelledby={`step-${n}`} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-4">
    <span aria-hidden className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-primary">{n}</span>
    <div className="space-y-3 min-w-0">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={`step-${n}`} className="text-base font-semibold text-text-primary">{title}</h2>
        {aside}
      </div>
      {children}
    </div>
  </section>
);

const Choice: React.FC<{ id: string; on: boolean; onPick: () => void; title: string; text: React.ReactNode; extra?: React.ReactNode }> = ({ id, on, onPick, title, text, extra }) => (
  <button
    id={id}
    type="button"
    role="radio"
    aria-checked={on}
    onClick={onPick}
    className={`flex-1 rounded-xl border px-4 py-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${
      on ? 'border-primary bg-accent-soft' : 'border-border bg-surface hover:border-text-muted'
    }`}
  >
    <span className={`block text-sm font-semibold ${on ? 'text-primary' : 'text-text-primary'}`}>{title}</span>
    <span className="mt-1 block text-xs text-text-secondary leading-relaxed">{text}</span>
    {extra && <span className="mt-1.5 block text-xs font-medium text-text-primary">{extra}</span>}
  </button>
);

export const Home: React.FC = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [workspaceLabel, setWorkspaceLabel] = useState<string>('');
  const [runName, setRunName] = useState<string>('');
  const [allowSubdirectories, setAllowSubdirectories] = useState<boolean>(true);
  // Unattended is the whole point of the choice: nothing pauses for a human,
  // so the run only comes back when it finishes or fails. Supervised keeps the
  // individual gates, which are then worth showing separately.
  const [unattended, setUnattended] = useState<boolean>(false);
  // Approval mode asks at decisions, not at every file: the review gates below
  // are where a person decides, so per-action prompts start switched off.
  const [autoApprove, setAutoApprove] = useState<boolean>(true);
  // How this run delivers. Chosen per run: it is not a setting of the models.
  const [deliveryMode, setDeliveryMode] = useState<'fast' | 'thorough'>('fast');
  // Whether the stages that need judgement use the frontier model. Off, every
  // stage runs on the local build model.
  const [useFrontierModel, setUseFrontierModel] = useState<boolean>(true);
  // Set once the server says no frontier model is configured. See the check below.
  const noFrontierModel = useRef(false);
  // Minutes a review gate waits for a person before approving itself; blank
  // waits however long it takes.
  const [approvalTimeout, setApprovalTimeout] = useState<string>('');
  // What a run of each delivery mode has typically taken here.
  const [forecast, setForecast] = useState<Record<string, RunForecast | null>>({});
  useEffect(() => {
    getOutcomes().then((data) => setForecast(data.forecast)).catch(() => setForecast({}));
  }, []);
  const [reviewIntake, setReviewIntake] = useState<boolean>(true);
  const [reviewTechSpec, setReviewTechSpec] = useState<boolean>(true);
  const [reviewAcceptance, setReviewAcceptance] = useState<boolean>(true);
  const [reviewSprint, setReviewSprint] = useState<boolean>(true);
  const [reviewRelease, setReviewRelease] = useState<boolean>(true);
  const [reviewEscalation, setReviewEscalation] = useState<boolean>(true);
  // The form opens as the owner last started a run (plan UI-S5): read once, and
  // only what was saved replaces the defaults above.
  useEffect(() => {
    let live = true;
    readRunDefaults().then((saved) => {
      if (!live || !saved) return;
      if (saved.delivery_mode) setDeliveryMode(saved.delivery_mode);
      if (saved.use_frontier_model !== undefined) setUseFrontierModel(saved.use_frontier_model && !noFrontierModel.current);
      if (saved.unattended !== undefined) setUnattended(saved.unattended);
      if (saved.auto_approve !== undefined) setAutoApprove(saved.auto_approve);
      if (saved.approval_timeout_minutes) setApprovalTimeout(String(saved.approval_timeout_minutes));
      if (saved.allow_subdirectories !== undefined) setAllowSubdirectories(saved.allow_subdirectories);
      const reviews = saved.reviews ?? {};
      const take = (key: string, set: (on: boolean) => void) => { if (key in reviews) set(reviews[key]); };
      take('product_intake', setReviewIntake);
      take('technical_specification', setReviewTechSpec);
      take('acceptance_tests', setReviewAcceptance);
      take('sprint', setReviewSprint);
      take('release', setReviewRelease);
      take('escalation', setReviewEscalation);
    });
    return () => {
      live = false;
    };
  }, []);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const navigate = useNavigate();
  const health = useServerHealth();
  const holder = holdingTheModel(health);
  // The brief as text, beside or instead of its files (plan BG.10); kept as a
  // draft in this browser until a run starts from it.
  const [briefText, setBriefText] = useState<string>(readDraft);
  // The text of the brief's text files, for the criteria preview.
  const [fileText, setFileText] = useState('');
  useEffect(() => {
    let live = true;
    const readable = files.filter((file) => /\.(md|txt)$/i.test(file.name));
    Promise.all(readable.map((file) => file.text()))
      .then((texts) => live && setFileText(texts.join('\n\n')))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [files]);
  // Who reviews the run: the person starting it.
  const [reviewer, setReviewer] = useState('');
  useEffect(() => {
    let live = true;
    api.get('/auth/me').then((me) => live && setReviewer(String(me.data?.username ?? ''))).catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  // The brief's size, from its criteria preview: the estimates scale with it.
  const [criteriaCount, setCriteriaCount] = useState<number | null>(null);
  // Whether the frontier model is configured and answering, asked when the box is ticked.
  const [frontier, setFrontier] = useState<FrontierStatus | null>(null);
  // With no frontier model configured the box starts unticked (owner, 2026-10-20):
  // a ticked box could only block the start. Asked once; a saved default cannot
  // tick it back. One that is configured and not answering stays ticked and says why.
  useEffect(() => {
    let live = true;
    getFrontierStatus()
      .then((found) => {
        if (!live || !found || found.configured) return;
        noFrontierModel.current = true;
        setFrontier(found);
        setUseFrontierModel(false);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (!useFrontierModel) return;
    let live = true;
    getFrontierStatus().then((found) => live && setFrontier(found)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [useFrontierModel]);
  // An existing codebase to start from, as an archive (a brownfield run).
  const [codebase, setCodebase] = useState<File | null>(null);
  const hasBrief = files.length > 0 || briefText.trim().length > 0;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(Array.from(e.target.files));
      setError(null);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(Array.from(e.dataTransfer.files));
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!hasBrief) {
      setError('Write the brief or add its documents.');
      return;
    }
    if (useFrontierModel) {
      const status = frontier ?? (await getFrontierStatus().catch(() => null));
      if (status?.problem) {
        setError(status.problem);
        return;
      }
    }

    setIsUploading(true);
    setError(null);

    // A run that was created but could not start is deleted, not left behind
    // as an orphan in the list (plan BG.10, G9).
    let created: string | null = null;
    try {
      const written = briefText.trim() ? [new File([briefText], 'brief.md', { type: 'text/markdown' })] : [];
      const runData = await createRun([...files, ...written]);
      created = runData.run_id;
      if (codebase) await uploadCodebase(runData.run_id, codebase);
      
      const payload: any = {
        // The person starting the run reviews it.
        reviewer: reviewer || undefined,
        name: runName.trim() || undefined,
        workspace_label: workspaceLabel || undefined,
        allow_subdirectories: allowSubdirectories,
        auto_approve: unattended || autoApprove,
        delivery_mode: deliveryMode,
        use_frontier_model: useFrontierModel,
        approval_timeout_minutes:
          !unattended && parseInt(approvalTimeout, 10) > 0 ? parseInt(approvalTimeout, 10) : undefined,
        review_policy: unattended
          ? { product_intake: false, technical_specification: false, acceptance_tests: false, sprint: false, release: false, escalation: false }
          : {
              product_intake: reviewIntake,
              technical_specification: reviewTechSpec,
              acceptance_tests: reviewAcceptance,
              sprint: reviewSprint,
              release: reviewRelease,
              escalation: reviewEscalation
            }
      };
      
      // Provider, model and base URL are deliberately NOT sent.
      //
      // They used to be copied here from the settings endpoint and posted as
      // per-run "overrides". They were never a choice - this page has no
      // control for picking a different model - so each run silently snapshotted
      // whatever global config happened to say at the moment it started, and
      // that snapshot then outranked the Settings page forever. Changing the
      // model or the endpoint afterwards could not reach a run that already
      // existed. A run now inherits current settings on every attempt.
      //
      // Per-run overrides still exist for API callers who genuinely want one;
      // this form just isn't one of them.

      await startRun(runData.run_id, payload);
      await saveRunDefaults({
        delivery_mode: deliveryMode,
        use_frontier_model: useFrontierModel,
        unattended,
        auto_approve: autoApprove,
        approval_timeout_minutes: parseInt(approvalTimeout, 10) > 0 ? parseInt(approvalTimeout, 10) : null,
        allow_subdirectories: allowSubdirectories,
        reviews: {
          product_intake: reviewIntake,
          technical_specification: reviewTechSpec,
          acceptance_tests: reviewAcceptance,
          sprint: reviewSprint,
          release: reviewRelease,
          escalation: reviewEscalation,
        },
      });
      keepDraft('');
      navigate(`/runs/${runData.run_id}`);
    } catch (err: any) {
      console.error(err);
      if (created) await deleteRun(created).catch(() => undefined);
      setError(err.response?.data?.detail || err.message || "An error occurred during upload.");
      setIsUploading(false);
    }
  };

  const involvement: Involvement = unattended ? 'hands_off' : autoApprove ? 'review_stages' : 'every_step';
  const chooseInvolvement = (next: Involvement) => {
    setUnattended(next === 'hands_off');
    setAutoApprove(next !== 'every_step');
  };
  const gates: Record<string, [boolean, (on: boolean) => void]> = {
    reviewIntake: [reviewIntake, setReviewIntake],
    reviewTechSpec: [reviewTechSpec, setReviewTechSpec],
    reviewAcceptance: [reviewAcceptance, setReviewAcceptance],
    reviewSprint: [reviewSprint, setReviewSprint],
    reviewRelease: [reviewRelease, setReviewRelease],
    reviewEscalation: [reviewEscalation, setReviewEscalation],
  };
  const gatesKept = Object.values(gates).filter(([on]) => on).length;
  const server = describeServer(health);
  const estimate = typicalTime(forecast[deliveryMode], criteriaCount);
  const whyNotYet = !hasBrief ? 'Write the brief or add its documents to start.' : null;
  const summary = [
    deliveryMode === 'fast' ? 'Fast' : 'Thorough',
    estimate || null,
    INVOLVEMENT.find((choice) => choice.id === involvement)?.title,
    useFrontierModel ? `local + frontier${frontier?.model ? ` (${frontier.model})` : ''}` : 'local model only',
    codebase ? 'from existing code' : null,
  ].filter(Boolean).join(' · ');

  return (
    <div className="mx-auto w-full max-w-3xl mt-4 animate-fade-in pb-28">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-text-primary">Start a new run</h1>
        <p className="mt-1 text-sm text-text-secondary">Describe what to build, choose how it runs, and start it.</p>
        {holder && (
          <p role="status" className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
            The model serves one request at a time and {holder} is on it: a run started now waits for it to free the model.
          </p>
        )}
      </header>

      <form onSubmit={handleSubmit} className="glass-card-strong rounded-2xl p-6 sm:p-8 space-y-8">
        <Step n={1} title="What to build">
          <Textarea
            label="Write the brief"
            hint="Kept in this browser until a run starts. Documents can be added beside it or instead of it."
            rows={8}
            value={briefText}
            onChange={(event) => { setBriefText(event.target.value); keepDraft(event.target.value); }}
            placeholder={'# What to build\n\n## Features\n- ...'}
          />
          <div
            className={`flex flex-wrap items-center gap-3 rounded-xl border-2 border-dashed px-4 py-3 text-sm transition-colors cursor-pointer ${
              isDragging ? 'border-primary bg-accent-soft' : files.length > 0 ? 'border-success/50 bg-success/5' : 'border-border hover:border-primary/50'
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-upload')?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                document.getElementById('file-upload')?.click();
              }
            }}
          >
            <input id="file-upload" type="file" multiple className="hidden" accept=".md,.txt,.pdf,.docx" onChange={handleFileChange} />
            {files.length === 0 ? (
              <>
                <UploadCloud className="h-5 w-5 text-text-muted" />
                <span className="text-text-secondary"><span className="font-medium text-text-primary">Add documents</span> - drop them here or click. Markdown, PDF, TXT or DOCX, up to 10 MB each.</span>
              </>
            ) : (
              <>
                <FileText className="h-5 w-5 text-success" />
                <span className="flex-1 min-w-0 truncate text-text-primary">{files.map((f) => f.name).join(', ')}</span>
                <button type="button" className="text-danger hover:underline" onClick={(e) => { e.stopPropagation(); setFiles([]); }}>Remove</button>
              </>
            )}
          </div>
          <CriteriaPreview onCount={setCriteriaCount} brief={[briefText, fileText].filter((part) => part.trim()).join('\n\n')} />
          <Input
            label="Run name"
            aside={<span className="text-xs text-text-muted">optional</span>}
            hint="Tells this run from the others in the list. You can change it later."
            maxLength={80}
            value={runName}
            onChange={(e) => setRunName(e.target.value)}
            placeholder="e.g., checkout rewrite, second try"
          />
        </Step>

        <Step n={2} title="Delivery">
          <div className="flex flex-col sm:flex-row gap-3" role="radiogroup" aria-label="Delivery">
            {(['fast', 'thorough'] as const).map((choice) => (
              <Choice
                key={choice}
                id={`delivery-${choice}`}
                on={deliveryMode === choice}
                onPick={() => setDeliveryMode(choice)}
                title={choice === 'fast' ? 'Fast' : 'Thorough'}
                text={choice === 'fast'
                  ? 'One sprint for a small product: files written from the specification, checks run by the harness.'
                  : 'Every sprint planned, built, tested and reviewed in full.'}
                extra={typicalTime(forecast[choice], criteriaCount) || undefined}
              />
            ))}
          </div>
          <p className="text-xs text-text-muted">
            {criteriaCount
              ? 'Estimates are for a brief of this size, from the most recent runs of each kind here.'
              : 'Times are what recent runs of each kind took here; with a brief, they are for its size.'}
          </p>
        </Step>

        <Step n={3} title="Your involvement">
          <div className="flex flex-col gap-3 md:flex-row" role="radiogroup" aria-label="Your involvement">
            {INVOLVEMENT.map((choice) => (
              <Choice key={choice.id} id={`involvement-${choice.id}`} on={involvement === choice.id} onPick={() => chooseInvolvement(choice.id)} title={choice.title} text={choice.text} />
            ))}
          </div>
          {involvement !== 'hands_off' && (
            <details className="group rounded-xl border border-border bg-surface/50">
              <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-text-primary flex items-center justify-between">
                <span>Reviews the run stops for</span>
                <span className="text-xs font-normal text-text-muted">{gatesKept} of {GATES.length} on &middot; change</span>
              </summary>
              <div className="space-y-3 border-t border-border px-4 py-3">
                {GATES.map(([key, label, hint]) => (
                  <Checkbox key={key} label={label} hint={hint} checked={gates[key][0]} onChange={(e) => gates[key][1](e.target.checked)} />
                ))}
                <label htmlFor="approvalTimeout" className="block pt-1 text-sm text-text-primary">
                  Approve a waiting review automatically after
                  <input
                    id="approvalTimeout"
                    type="number"
                    min={1}
                    max={10080}
                    value={approvalTimeout}
                    onChange={(e) => setApprovalTimeout(e.target.value)}
                    placeholder="never"
                    className="mx-2 w-20 rounded-md border border-border bg-surface px-2 py-1 text-sm"
                  />
                  minutes
                  <span className="block text-xs text-text-muted mt-1">Blank waits for you however long it takes.</span>
                </label>
              </div>
            </details>
          )}
        </Step>

        <Step n={4} title="Model" aside={<Link to="/settings?tab=models" className="text-sm font-medium text-primary hover:underline">Change in Settings</Link>}>
          <p className={`rounded-xl border border-border bg-surface px-4 py-3 text-sm ${server.tone === 'warn' ? 'text-warning' : 'text-text-secondary'}`}>{server.said}</p>
          <Checkbox
            label="Use the frontier model"
            hint="The specification, the reviews and escalated fixes run on the frontier model set in Settings. Off, every stage runs on the local model."
            checked={useFrontierModel}
            onChange={(e) => setUseFrontierModel(e.target.checked)}
          />
          {useFrontierModel && frontier && (
            frontier.problem ? (
              <p role="alert" className="text-xs text-warning">
                {frontier.problem} <Link to="/settings?tab=models" className="font-medium underline">Open the model settings</Link>
              </p>
            ) : (
              <p className="text-xs text-success">Ready: {frontier.model} on {frontier.provider} answers.</p>
            )
          )}
        </Step>

        <details className="rounded-xl border border-border bg-surface/50">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-text-primary flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-text-muted" /> Advanced
            <span className="text-xs font-normal text-text-muted">existing code, workspace name, folder access</span>
          </summary>
          <div className="space-y-5 border-t border-border px-4 py-4">
            <div>
              <label htmlFor="codebase-upload" className="block text-sm font-medium text-text-primary mb-1">Start from existing code</label>
              <input
                id="codebase-upload"
                type="file"
                accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2,.tbz2,.tar.xz"
                onChange={(event) => setCodebase(event.target.files?.[0] ?? null)}
                className="text-sm text-text-secondary"
              />
              <p className="text-xs text-text-muted mt-1">An archive of the repository; the run builds on it instead of starting empty.</p>
            </div>
            <Input
              label="Workspace name"
              hint="A label, not a path: every run has its own workspace on the server, and this makes it recognisable on disk."
              maxLength={48}
              value={workspaceLabel}
              onChange={(e) => setWorkspaceLabel(e.target.value)}
              placeholder="e.g., checkout-service"
            />
            <Checkbox
              label="Let agents work in subfolders of the workspace"
              hint="Off, they work in its root only."
              checked={allowSubdirectories}
              onChange={(e) => setAllowSubdirectories(e.target.checked)}
            />
          </div>
        </details>

        {/* What is about to start, with the one action, always in view. */}
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1 text-sm">
              {error ? (
                <p role="alert" className="text-danger">{error}</p>
              ) : (
                <p className="truncate text-text-secondary" title={summary}>{whyNotYet ?? summary}</p>
              )}
            </div>
            <Button type="submit" variant="primary" disabled={!hasBrief || isUploading} loading={isUploading} icon={<PlayCircle className="h-5 w-5" />} className="px-6 py-2.5 text-base">
              {isUploading ? 'Starting...' : 'Start Workflow Run'}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
};
