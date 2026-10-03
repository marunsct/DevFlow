import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileText, PlayCircle, FolderOpen, ShieldCheck, CheckSquare } from 'lucide-react';
import { createRun, startRun } from '../api';

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
  const [reviewIntake, setReviewIntake] = useState<boolean>(true);
  const [reviewTechSpec, setReviewTechSpec] = useState<boolean>(true);
  const [reviewAcceptance, setReviewAcceptance] = useState<boolean>(true);
  const [reviewSprint, setReviewSprint] = useState<boolean>(true);
  const [reviewRelease, setReviewRelease] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const navigate = useNavigate();

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
        review_policy: unattended
          ? { product_intake: false, technical_specification: false, acceptance_tests: false, sprint: false, release: false }
          : {
              product_intake: reviewIntake,
              technical_specification: reviewTechSpec,
              acceptance_tests: reviewAcceptance,
              sprint: reviewSprint,
              release: reviewRelease
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
      navigate(`/runs/${runData.run_id}`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || err.message || "An error occurred during upload.");
      setIsUploading(false);
    }
  };

  const Checkbox = ({ id, checked, onChange, label, description }: {
    id: string; checked: boolean; onChange: (v: boolean) => void; label: string; description?: string;
  }) => (
    <label htmlFor={id} className="flex items-start gap-3 cursor-pointer group">
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
            <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
      </div>
      <div>
        <span className="text-sm font-medium text-text-primary group-hover:text-white transition-colors">{label}</span>
        {description && <p className="text-xs text-text-muted mt-0.5">{description}</p>}
      </div>
    </label>
  );

  return (
    <div className="max-w-3xl mx-auto mt-4 animate-fade-in">
      <div className="glass-card-strong rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-8 text-center border-b border-border/50 bg-gradient-to-b from-primary/5 to-transparent">
          <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-gradient-to-br from-primary/20 to-violet-500/20 border border-primary/30 mb-4">
            <PlayCircle className="h-7 w-7 text-primary" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Start New Workflow</h1>
          <p className="text-text-secondary text-sm max-w-md mx-auto">
            Upload your product documents to kick off the automated development pipeline.
          </p>
        </div>

        {/* Form */}
        <div className="p-8">
          <form onSubmit={handleSubmit}>
            {/* Upload Area */}
            <div
              className={`border-2 border-dashed rounded-xl p-10 text-center transition-all duration-300 cursor-pointer ${
                isDragging
                  ? 'border-primary bg-primary/10 scale-[1.01]'
                  : files.length > 0
                    ? 'border-success/50 bg-success/5'
                    : 'border-border hover:border-primary/50 hover:bg-white/[0.02]'
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => document.getElementById('file-upload')?.click()}
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
                  <h3 className="text-base font-semibold text-text-primary mb-1">
                    Drop files here or click to browse
                  </h3>
                  <p className="text-sm text-text-muted">
                    Markdown, PDF, TXT or DOCX (max 10MB each)
                  </p>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="h-14 w-14 bg-success/10 rounded-xl flex items-center justify-center mb-4">
                    <FileText className="h-7 w-7 text-success" />
                  </div>
                  <h3 className="text-base font-semibold text-white mb-2">
                    {files.length} file{files.length > 1 ? 's' : ''} selected
                  </h3>
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
                    className="text-sm text-danger hover:text-danger/80 transition-colors"
                    onClick={(e) => { e.stopPropagation(); setFiles([]); }}
                  >
                    Remove all files
                  </button>
                </div>
              )}
            </div>

            {/* Configuration */}
            <div className="mt-8 space-y-6">
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
                  className="w-full px-4 py-2.5 bg-surface border border-border rounded-xl text-white placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 transition-all text-sm"
                />
                <p className="text-xs text-text-muted mt-1.5">
                  Just a label, not a path. Every run gets its own isolated workspace on the
                  server either way &mdash; this only makes it recognisable on disk. Documents go
                  to <code className="text-primary/80">docs/</code> and code
                  to <code className="text-primary/80">{'<product-name>'}/</code> inside it.
                </p>
              </div>

              {/* How much the run should stop for you */}
              <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-4">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-primary" />
                  Supervision
                </h3>
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

              {/* Only meaningful when the run is supervised */}
              {!unattended && (
                <>
                  <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-4">
                    <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-primary" />
                      Approvals
                    </h3>
                    <Checkbox
                      id="autoApprove"
                      checked={autoApprove}
                      onChange={setAutoApprove}
                      label="Auto-approve file writes and tool calls"
                      description="Skip the per-action prompt. Review gates below still stop the run."
                    />
                  </div>

                  <div className="p-4 rounded-xl bg-surface/50 border border-border/50 space-y-4">
                    <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                      <CheckSquare className="h-4 w-4 text-primary" />
                      Review Gates
                    </h3>
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
                  </div>
                </>
              )}
            </div>

            {/* Error */}
            {error && (
              <div className="mt-6 p-4 bg-danger/10 border border-danger/30 rounded-xl text-danger text-sm flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-danger animate-pulse shrink-0" />
                {error}
              </div>
            )}

            {/* Submit */}
            <div className="mt-8">
              <button
                type="submit"
                disabled={files.length === 0 || isUploading}
                className={`w-full flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl font-semibold text-white transition-all ${
                  files.length === 0 || isUploading
                    ? 'bg-surface-overlay text-text-muted cursor-not-allowed'
                    : 'gradient-btn'
                }`}
              >
                {isUploading ? (
                  <>
                    <div className="h-5 w-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
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
          </form>
        </div>
      </div>
    </div>
  );
};
