import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileText, PlayCircle, FolderOpen, ShieldCheck, CheckSquare } from 'lucide-react';
import { createRun, startRun, getOutcomes, type RunForecast } from '../api';
import { holdingTheModel, useServerHealth } from '../lib/serverHealth';
import { readRunDefaults, saveRunDefaults } from '../lib/runDefaults';

export const Home: React.FC = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [workspaceLabel, setWorkspaceLabel] = useState<string>('');
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
      if (saved.use_frontier_model !== undefined) setUseFrontierModel(saved.use_frontier_model);
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
  const holder = holdingTheModel(useServerHealth());

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
    if (files.length === 0) {
      setError("Please select at least one file to upload.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const runData = await createRun(files);
      
      const payload: any = {
        reviewer: "Product Manager",
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
      navigate(`/runs/${runData.run_id}`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || err.message || "An error occurred during upload.");
      setIsUploading(false);
    }
  };

interface CheckboxProps {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}

const Checkbox: React.FC<CheckboxProps> = ({ id, checked, onChange, label, description }) => (
  <label className="flex items-start gap-3 cursor-pointer group">
    <div className="relative mt-0.5">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
      <div className={`h-5 w-5 rounded-md border-2 transition-all duration-200 flex items-center justify-center ${
        checked
          ? 'bg-primary border-primary shadow-lg shadow-primary/20'
          : 'border-border bg-surface hover:border-text-muted'
      }`}>
        {checked && (
          <svg className="h-3 w-3 text-text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        )}
      </div>
    </div>
    <div>
      <span className="text-sm font-medium text-text-primary group-hover:text-text-primary transition-colors">{label}</span>
      {description && <p className="text-xs text-text-muted mt-0.5">{description}</p>}
    </div>
  </label>
);

  return (
    <div className="w-full mt-4 animate-fade-in">
      <div className="glass-card-strong rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-8 text-center border-b border-border/50 bg-gradient-to-b from-primary/5 to-transparent">
          <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-gradient-to-br from-primary/20 to-accent-soft border border-primary/30 mb-4">
            <PlayCircle className="h-7 w-7 text-primary" />
          </div>
          <h1 className="text-2xl font-bold text-text-primary mb-2">Start New Workflow</h1>
          <p className="text-text-secondary text-sm max-w-md mx-auto">
            Upload your product documents to kick off the automated development pipeline.
          </p>
          {holder && (
            <p role="status" className="mt-3 text-xs text-warning max-w-md mx-auto">
              The model serves one request at a time and {holder} is on it: a run started now waits for it to free the model.
            </p>
          )}
        </div>

        {/* Form */}
        <div className="p-8">
          <form onSubmit={handleSubmit}>
            {/* Two columns on a wide screen: what the run is built from, and how it runs. */}
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-8 items-start">
            <div className="space-y-6">
            {/* Upload Area */}
            <div
              className={`border-2 border-dashed rounded-xl p-10 text-center transition-all duration-300 cursor-pointer ${
                isDragging
                  ? 'border-primary bg-accent-soft scale-[1.01]'
                  : files.length > 0
                    ? 'border-success/50 bg-success/5'
                    : 'border-border hover:border-primary/50 hover:bg-overlay'
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
              <input
                id="file-upload"
                type="file"
                multiple
                className="hidden"
                accept=".md,.txt,.pdf,.docx"
                onChange={handleFileChange}
              />

              {files.length === 0 ? (
                <div className="flex flex-col items-center">
                  <div className="h-14 w-14 bg-surface-overlay/50 rounded-xl flex items-center justify-center mb-4">
                    <UploadCloud className="h-7 w-7 text-text-muted" />
                  </div>
                  <h2 className="text-base font-semibold text-text-primary mb-1">
                    Drop files here or click to browse
                  </h2>
                  <p className="text-sm text-text-muted">
                    Markdown, PDF, TXT or DOCX (max 10MB each)
                  </p>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="h-14 w-14 bg-success-bg rounded-xl flex items-center justify-center mb-4">
                    <FileText className="h-7 w-7 text-success" />
                  </div>
                  <h2 className="text-base font-semibold text-text-primary mb-2">
                    {files.length} file{files.length > 1 ? 's' : ''} selected
                  </h2>
                  <ul className="text-sm text-text-secondary max-h-24 overflow-y-auto mb-3 w-full max-w-sm text-left space-y-1">
                    {files.map((f, i) => (
                      <li key={i} className="truncate flex items-center gap-2">
                        <FileText className="h-3.5 w-3.5 text-text-muted shrink-0" />
                        <span>{f.name}</span>
                        <span className="text-text-muted">({(f.size / 1024 / 1024).toFixed(2)} MB)</span>
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="text-sm text-danger hover:text-danger transition-colors"
                    onClick={(e) => { e.stopPropagation(); setFiles([]); }}
                  >
                    Remove all files
                  </button>
                </div>
              )}
            </div>

              {/* Workspace label */}
              <div>
                <label htmlFor="workspace-label" className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2">
                  <FolderOpen className="h-4 w-4 text-primary" />
                  Workspace name <span className="font-normal text-text-muted">(optional)</span>
                </label>
                <input
                  id="workspace-label"
                  type="text"
                  maxLength={48}
                  value={workspaceLabel}
                  onChange={(e) => setWorkspaceLabel(e.target.value)}
                  placeholder="e.g., checkout-service"
                  className="w-full px-4 py-2.5 bg-surface border border-border rounded-xl text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all text-sm"
                />
                <p className="text-xs text-text-muted mt-1.5">
                  Just a label, not a path. Every run gets its own isolated workspace on the
                  server either way &mdash; this only makes it recognisable on disk. Documents go
                  to <code className="text-primary">docs/</code> and code
                  to <code className="text-primary">{'<product-name>'}/</code> inside it.
                </p>
              </div>

            {/* Error */}
            {error && (
              <div className="p-4 bg-danger-bg border border-danger/30 rounded-xl text-danger text-sm flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-danger animate-pulse shrink-0" />
                {error}
              </div>
            )}

            {/* Submit */}
            <div>
              <button
                type="submit"
                disabled={files.length === 0 || isUploading}
                className={`w-full flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl font-semibold text-primary-foreground transition-all ${
                  files.length === 0 || isUploading
                    ? 'bg-surface-overlay text-text-muted cursor-not-allowed'
                    : 'gradient-btn'
                }`}
              >
                {isUploading ? (
                  <>
                    <div className="h-5 w-5 border-2 border-border border-t-text-primary rounded-full animate-spin" />
                    Starting Workflow...
                  </>
                ) : (
                  <>
                    <PlayCircle className="h-5 w-5" />
                    Start Workflow Run
                  </>
                )}
              </button>
            </div>
            </div>

            {/* Configuration */}
            <div className="space-y-6 xl:mt-0">
              {/* How much the run should stop for you */}
              <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-4">
                <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-primary" />
                  Supervision
                </h2>
                <Checkbox
                  id="unattended"
                  checked={unattended}
                  onChange={setUnattended}
                  label="Run unattended"
                  description="Nothing pauses for you. Every file write and tool call is approved automatically and all review gates are skipped, so the run comes back only when the product is complete or something fails."
                />
                <Checkbox
                  id="allowSubdirectories"
                  checked={allowSubdirectories}
                  onChange={setAllowSubdirectories}
                  label="Grant subdirectory access"
                  description="Let agents work in subdirectories of this run's workspace, not just its root."
                />
              </div>

              <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-3">
                <h2 className="text-sm font-semibold text-text-primary">Delivery</h2>
                <div className="flex flex-col sm:flex-row gap-3" role="radiogroup" aria-label="Delivery">
                  {(['fast', 'thorough'] as const).map((choice) => (
                    <button
                      key={choice}
                      id={`delivery-${choice}`}
                      type="button"
                      role="radio"
                      aria-checked={deliveryMode === choice}
                      onClick={() => setDeliveryMode(choice)}
                      className={`flex-1 rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition-all ${
                        deliveryMode === choice
                          ? 'border-primary bg-accent-soft text-primary'
                          : 'border-border/50 bg-surface/30 text-text-muted hover:text-text-secondary hover:border-border'
                      }`}
                    >
                      {choice === 'fast' ? 'Fast' : 'Thorough'}
                      <span className="block text-xs font-normal mt-0.5">
                        {choice === 'fast'
                          ? 'One sprint for a small product, files written from the specification, harness-run checks'
                          : 'Every sprint planned, built, tested and reviewed in full'}
                      </span>
                    </button>
                  ))}
                </div>
                {forecast[deliveryMode] && (
                  <p className="text-xs text-text-secondary">
                    A completed {deliveryMode} run here has typically taken {forecast[deliveryMode]!.typical_hours} h
                    ({forecast[deliveryMode]!.shortest_hours}-{forecast[deliveryMode]!.longest_hours} h over{' '}
                    {forecast[deliveryMode]!.runs} runs).
                  </p>
                )}
                <p className="text-xs text-text-muted leading-relaxed">
                  Both keep the project in memory for every stage and check each edit as it is written.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-3">
                <h2 className="text-sm font-semibold text-text-primary">Models</h2>
                <Checkbox
                  id="useFrontierModel"
                  checked={useFrontierModel}
                  onChange={setUseFrontierModel}
                  label="Use the frontier model"
                  description="The specification, the reviews and escalated fixes run on the frontier model set in Settings. Unchecked, every stage of this run - planning, building, testing and reviews - runs on the local model only."
                />
              </div>

              {/* Only meaningful when the run is supervised */}
              {!unattended && (
                <>
                  <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-4">
                    <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-primary" />
                      Approvals
                    </h2>
                    <Checkbox
                      id="autoApprove"
                      checked={autoApprove}
                      onChange={setAutoApprove}
                      label="Auto-approve file writes and tool calls"
                      description="Skip the per-action prompt. Review gates below still stop the run."
                    />
                  </div>

                  <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-4">
                    <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                      <CheckSquare className="h-4 w-4 text-primary" />
                      Review Gates
                    </h2>
                    <label htmlFor="approvalTimeout" className="block text-sm text-text-primary">
                      Approve a waiting gate automatically after
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
                      <span className="block text-xs text-text-muted mt-1">
                        Leave blank to wait for you however long it takes.
                      </span>
                    </label>
                    <Checkbox
                      id="reviewIntake"
                      checked={reviewIntake}
                      onChange={setReviewIntake}
                      label="Product Intake Review"
                    />
                    <Checkbox
                      id="reviewTechSpec"
                      checked={reviewTechSpec}
                      onChange={setReviewTechSpec}
                      label="Technical Specification Review"
                    />
                    <Checkbox
                      id="reviewAcceptance"
                      checked={reviewAcceptance}
                      onChange={setReviewAcceptance}
                      label="Acceptance Tests Review"
                      description="The tests that decide when the product is done, before they are locked."
                    />
                    <Checkbox
                      id="reviewSprint"
                      checked={reviewSprint}
                      onChange={setReviewSprint}
                      label="End of Sprint Review"
                      description="With the criteria that pass, screenshots and decisions. A requested change becomes a tracked change request."
                    />
                    <Checkbox
                      id="reviewRelease"
                      checked={reviewRelease}
                      onChange={setReviewRelease}
                      label="Release Review"
                      description="The finished product, once every acceptance criterion passes."
                    />
                    <Checkbox
                      id="reviewEscalation"
                      checked={reviewEscalation}
                      onChange={setReviewEscalation}
                      label="Ask Me When Work Is Stuck"
                      description="A sprint that fixes and re-planning cannot finish, or a specification its review never approves: you decide to go on (deferring what fails, or building from the latest design) or try again with your guidance. Off, the run decides and records why."
                    />
                  </div>
                </>
              )}
            </div>

            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
