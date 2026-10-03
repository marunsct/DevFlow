import React, { useEffect, useState } from 'react';
import { Server, User, Shield, Info, Save, Trash2 } from 'lucide-react';
import { api } from '../api';

import type { ModelProfile, SettingsView } from '../types';

/** What the form can change.
 *
 *  Credentials are write-only: the server never returns one, so the inputs
 *  start empty and are only sent when the operator actually types something.
 *  Sending "" deletes the stored credential and lets the deployment's own
 *  environment apply again. */
interface ProviderForm {
  llm_provider: string;
  openai_base_url: string;
  model_name: string;
  model_context_window: number;
  model_max_output_tokens: number;
  thinking_mode: 'default' | 'on' | 'off';
  thinking_effort: 'low' | 'medium' | 'high';
  execution_mode: 'linear' | 'parallel';
  openai_api_key?: string;
  anthropic_api_key?: string;
  google_api_key?: string;
  judgement_provider: string;
  judgement_base_url: string;
  judgement_model_name: string;
  judgement_context_window: number;
  judgement_api_key?: string;
}

type CredentialField = 'openai_api_key' | 'anthropic_api_key' | 'google_api_key' | 'judgement_api_key';

/** What each derived budget is, in words a reader can check against their model. */
const DERIVED_LABELS: Array<[string, string, string]> = [
  ['reply_ceiling_tokens', 'Longest single reply', 'tokens'],
  ['input_ceiling_tokens', 'Room for the conversation', 'tokens'],
  ['compaction_trigger_tokens', 'Summarises the conversation at', 'tokens'],
  ['protected_tail_tokens', 'Recent messages kept as-is', 'tokens'],
  ['document_budget_chars', 'Most of a document read at once', 'characters'],
  ['command_output_bytes', 'Output kept from one command', 'bytes'],
];

export const Settings: React.FC = () => {
  const [user, setUser] = useState<{ username: string; role?: string } | null>(null);
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const [saving, setSaving] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [detectNote, setDetectNote] = useState('');
  const [message, setMessage] = useState('');
  // Every configuration applied before, so switching back to a model is a pick
  // from this list rather than six fields typed again.
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [chosenProfile, setChosenProfile] = useState('');
  // Held apart from `settings` because these are never read back from the
  // server: an empty box means "leave it alone", not "there is no key".
  const [credentials, setCredentials] = useState<Record<CredentialField, string>>({
    openai_api_key: '',
    anthropic_api_key: '',
    google_api_key: '',
    judgement_api_key: '',
  });

  useEffect(() => {
    api.get('/auth/me').then(res => setUser(res.data)).catch(() => {});
    api.get('/settings').then(res => setSettings(res.data)).catch(() => {});
    loadProfiles();
  }, []);

  const loadProfiles = () => {
    api.get('/settings/models').then(res => setProfiles(res.data)).catch(() => {});
  };

  /** Fill the form from a saved model. Nothing changes until Save Settings. */
  const applyProfile = (id: string) => {
    setChosenProfile(id);
    const profile = profiles.find(p => p.id === id);
    if (!profile || !settings) return;
    setSettings({
      ...settings,
      llm_provider: profile.llm_provider ?? settings.llm_provider,
      openai_base_url: profile.openai_base_url ?? settings.openai_base_url,
      model_name: profile.model_name ?? settings.model_name,
      model_context_window: profile.model_context_window ?? settings.model_context_window,
      model_max_output_tokens: profile.model_max_output_tokens ?? 0,
      thinking_mode: profile.thinking_mode ?? 'default',
      thinking_effort: profile.thinking_effort ?? 'medium',
    });
    setMessage('Filled from a saved model. Save Settings to apply it.');
  };

  const forgetProfile = async () => {
    if (!chosenProfile) return;
    try {
      await api.delete(`/settings/models/${chosenProfile}`);
      setChosenProfile('');
      loadProfiles();
      setMessage('Saved model removed.');
    } catch (err: any) {
      setMessage(err.response?.data?.detail ?? 'Could not remove the saved model.');
    }
  };

  const CredentialField = ({ label, field, configured, hint, placeholder }: {
    label: string; field: CredentialField; configured: boolean;
    hint?: string | null; placeholder: string;
  }) => (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <label className="text-sm font-medium text-text-secondary">{label}</label>
        <span className={configured ? 'text-xs font-mono text-success' : 'text-xs text-text-muted'}>
          {configured ? (hint ?? 'configured') : 'not configured'}
        </span>
      </div>
      <input
        type="password"
        autoComplete="new-password"
        value={credentials[field]}
        onChange={(e) => setCredentials({ ...credentials, [field]: e.target.value })}
        className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-primary"
        placeholder={configured ? 'Leave blank to keep the stored key' : placeholder}
      />
    </div>
  );

  const InfoRow = ({ label, value }: { label: string; value: string }) => (
    <div className="flex justify-between items-center py-3 border-b border-border/30 last:border-0">
      <span className="text-sm text-text-secondary">{label}</span>
      <span className="text-sm font-medium text-text-primary font-mono">{value}</span>
    </div>
  );

  /** Ask the server what its context window actually is.
   *
   * The window is the one setting that has to be right and the one nobody
   * reliably knows: a model's advertised window is not what it was loaded
   * with, and no standard endpoint reports it. The server will say, though,
   * when asked to refuse something too large. */
  const detectWindow = async () => {
    setDetecting(true);
    setDetectNote('');
    try {
      const res = await api.post('/settings/detect-context-window');
      setDetectNote(res.data.explanation);
      if (res.data.detected && settings) {
        setSettings({ ...settings, model_context_window: res.data.detected });
      }
    } catch (err: any) {
      setDetectNote(err.response?.data?.detail ?? 'Could not reach the model server.');
    } finally {
      setDetecting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    setMessage('');
    try {
      const form: ProviderForm = {
        llm_provider: settings.llm_provider,
        openai_base_url: settings.openai_base_url,
        model_name: settings.model_name,
        model_context_window: settings.model_context_window,
        model_max_output_tokens: settings.model_max_output_tokens ?? 0,
        thinking_mode: settings.thinking_mode ?? 'default',
        thinking_effort: settings.thinking_effort ?? 'medium',
        execution_mode: settings.execution_mode ?? 'linear',
        judgement_provider: settings.judgement_provider ?? '',
        judgement_base_url: settings.judgement_base_url ?? '',
        judgement_model_name: settings.judgement_model_name ?? '',
        judgement_context_window: settings.judgement_context_window ?? 0,
      };
      // Only send a credential the operator actually typed into. An untouched
      // box must not clear a key that is already working.
      (Object.keys(credentials) as CredentialField[]).forEach((field) => {
        if (credentials[field] !== '') form[field] = credentials[field];
      });

      const res = await api.put('/settings', form);
      setSettings(res.data);
      setCredentials({ openai_api_key: '', anthropic_api_key: '', google_api_key: '', judgement_api_key: '' });
      setMessage('Settings saved. This model is now in Saved models.');
      setChosenProfile('');
      loadProfiles();
    } catch (err: any) {
      setMessage(err.response?.data?.detail ?? 'Could not save settings.');
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(''), 3000);
    }
  };

  return (
    <div className="max-w-3xl mx-auto mt-4 space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Settings</h1>
        <p className="text-text-secondary text-sm">View system configuration and account details.</p>
      </div>

      {/* Account */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <User className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-white">Account</h2>
        </div>
        <div className="px-6 py-2">
          <InfoRow label="Username" value={user?.username || 'Loading...'} />
          <InfoRow label="Role" value={user?.role ?? "-"} />
          <InfoRow label="Session" value="Active" />
        </div>
      </div>

      {/* Server Configuration */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <Server className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-white">AI Provider Configuration</h2>
        </div>
        <div className="px-6 py-4">
          {!settings ? (
            <p className="text-sm text-text-muted">Loading settings...</p>
          ) : (
            <form onSubmit={handleSave} className="space-y-4">
              {profiles.length > 0 && (
                <div className="rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                  <label
                    htmlFor="saved-models"
                    className="block text-sm font-medium text-text-secondary mb-1"
                  >
                    Saved models
                  </label>
                  <div className="flex items-center gap-2">
                    <select
                      id="saved-models"
                      value={chosenProfile}
                      onChange={(e) => applyProfile(e.target.value)}
                      className="flex-1 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                    >
                      <option value="">Choose a model you have used before...</option>
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                          {p.model_context_window ? ` - ${p.model_context_window.toLocaleString()} tokens` : ''}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={forgetProfile}
                      disabled={!chosenProfile}
                      title="Remove this saved model"
                      aria-label="Remove this saved model"
                      className="rounded-lg border border-border/50 p-2 text-text-secondary hover:text-white hover:border-primary/50 disabled:opacity-40 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <p className="mt-1.5 text-xs text-text-muted leading-relaxed">
                    Every model you save is kept here with its endpoint, context window,
                    reply limit and thinking settings. Picking one fills the form below;
                    API keys are never stored with it.
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">Provider</label>
                <select
                  value={settings.llm_provider}
                  onChange={(e) => setSettings({ ...settings, llm_provider: e.target.value })}
                  className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                >
                  <option value="local">Local (LM Studio / Ollama)</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">Model Name</label>
                <input
                  type="text"
                  value={settings.model_name}
                  onChange={(e) => setSettings({ ...settings, model_name: e.target.value })}
                  className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                  placeholder="e.g. gpt-4o, claude-3-5-sonnet-20241022"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">
                  Context window
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={32000}
                    step={1000}
                    value={settings.model_context_window}
                    onChange={(e) =>
                      setSettings({ ...settings, model_context_window: Number(e.target.value) || 0 })
                    }
                    className="w-40 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white tabular-nums focus:outline-none focus:border-primary"
                  />
                  <span className="text-xs text-text-muted">tokens</span>
                  <button
                    type="button"
                    onClick={detectWindow}
                    disabled={detecting}
                    className="ml-auto rounded-lg border border-border/50 px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-white hover:border-primary/50 disabled:opacity-50 transition-colors"
                  >
                    {detecting ? 'Asking the model…' : 'Detect'}
                  </button>
                </div>
                {detectNote && (
                  <p className="mt-1.5 text-xs text-text-secondary leading-relaxed">{detectNote}</p>
                )}
                <p className="mt-1.5 text-xs text-text-muted leading-relaxed">
                  Set this to what the model you selected actually has. Everything else the
                  workflow measures - when it summarises the conversation, how much of a
                  document it reads at once, how much output it keeps from a command - is
                  worked out from this one number. Setting it higher than the model really
                  is will not fail straight away; it fails hours later, mid-run.
                </p>

                <div className="mt-4">
                  <label
                    htmlFor="max-output"
                    className="block text-sm font-medium text-text-secondary mb-1"
                  >
                    Longest single reply
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="max-output"
                      type="number"
                      min={0}
                      step={1000}
                      value={settings.model_max_output_tokens ?? 0}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          model_max_output_tokens: Number(e.target.value) || 0,
                        })
                      }
                      className="w-40 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white tabular-nums focus:outline-none focus:border-primary"
                    />
                    <span className="text-xs text-text-muted">tokens</span>
                  </div>
                  <p className="mt-1.5 text-xs text-text-muted leading-relaxed">
                    The reply and the conversation share the window above, so raising
                    this shrinks the room the conversation has - the figures below
                    update to show what is left. Set 0 to let it follow the window.
                  </p>
                </div>

                {/* Thinking sits under the window because its budget is a
                    share of the reply ceiling above, not a separate allowance.
                    Showing the resulting token count is what makes the
                    trade-off visible: every token spent thinking is one the
                    answer cannot use. */}
                <div className="mt-4 rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                  <label
                    htmlFor="thinking-mode"
                    className="block text-sm font-medium text-text-secondary mb-1"
                  >
                    Thinking
                  </label>
                  <select
                    id="thinking-mode"
                    value={settings.thinking_mode ?? 'default'}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        thinking_mode: e.target.value as 'default' | 'on' | 'off',
                      })
                    }
                    className="w-64 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                  >
                    <option value="default">Leave the model server's setting alone</option>
                    <option value="on">Think before answering</option>
                    <option value="off">Do not think</option>
                  </select>

                  {settings.thinking_mode === 'on' && (
                    <div className="mt-3 pl-6.5">
                      <label
                        htmlFor="thinking-effort"
                        className="block text-xs font-medium text-text-secondary mb-1"
                      >
                        How much thinking
                      </label>
                      <div className="flex items-center gap-2">
                        <select
                          id="thinking-effort"
                          value={settings.thinking_effort ?? 'medium'}
                          onChange={(e) =>
                            setSettings({
                              ...settings,
                              thinking_effort: e.target.value as 'low' | 'medium' | 'high',
                            })
                          }
                          className="w-40 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                        >
                          <option value="low">Low - a quarter of the reply</option>
                          <option value="medium">Medium - half the reply</option>
                          <option value="high">High - three quarters</option>
                        </select>
                        {settings.thinking_budget_tokens ? (
                          <span className="text-xs text-text-muted tabular-nums">
                            {settings.thinking_budget_tokens.toLocaleString()} tokens
                          </span>
                        ) : null}
                      </div>
                    </div>
                  )}

                  <p className="mt-2.5 text-xs text-text-muted leading-relaxed">
                    "Do not think" is not the same as leaving it alone: a server started
                    with reasoning enabled keeps it under the first option. Only models
                    that support reasoning use this. Thinking tokens come out of the reply
                    budget above, so a higher setting leaves less room for the answer.
                  </p>
                </div>

                {/* The consequences of the number above. Shown because the
                    number on its own is not checkable by eye - the failures it
                    causes appear hours later in an unrelated stage. */}
                {settings.derived_budgets && (
                  <dl className="mt-3 rounded-lg border border-border/50 bg-surface/30 px-3 py-2.5 space-y-1">
                    {DERIVED_LABELS.filter(([key]) => settings.derived_budgets?.[key] !== undefined).map(
                      ([key, label, unit]) => (
                        <div key={key} className="flex items-baseline justify-between gap-3">
                          <dt className="text-xs text-text-muted">{label}</dt>
                          <dd className="text-xs font-medium text-text-secondary tabular-nums">
                            {settings.derived_budgets![key].toLocaleString()}
                            <span className="ml-1 text-text-muted font-normal">{unit}</span>
                          </dd>
                        </div>
                      ),
                    )}
                    <p className="pt-1.5 text-[11px] text-text-muted leading-relaxed">
                      Saved values. These update when you save a new window.
                    </p>
                  </dl>
                )}
              </div>

              {/* Execution Mode */}
              <div className="mt-4 rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                <label className="block text-sm font-medium text-text-secondary mb-1">Execution Mode</label>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setSettings({ ...settings, execution_mode: 'linear' })}
                    className={`flex-1 rounded-lg border px-3 py-2.5 text-sm font-medium transition-all ${
                      settings.execution_mode === 'linear'
                        ? 'border-primary bg-primary/15 text-primary'
                        : 'border-border/50 bg-surface/30 text-text-muted hover:text-text-secondary hover:border-border'
                    }`}
                  >
                    🔗 Linear
                    <span className="block text-[11px] font-normal mt-0.5 opacity-70">Stages run one at a time</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSettings({ ...settings, execution_mode: 'parallel' })}
                    className={`flex-1 rounded-lg border px-3 py-2.5 text-sm font-medium transition-all ${
                      settings.execution_mode === 'parallel'
                        ? 'border-primary bg-primary/15 text-primary'
                        : 'border-border/50 bg-surface/30 text-text-muted hover:text-text-secondary hover:border-border'
                    }`}
                  >
                    ⚡ Parallel
                    <span className="block text-[11px] font-normal mt-0.5 opacity-70">Specialist tasks fan out concurrently</span>
                  </button>
                </div>
                <p className="mt-2 text-xs text-text-muted leading-relaxed">
                  Linear is safer with models that have limited context or rate limits.
                  Parallel is faster when the model can handle concurrent requests.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">Base URL</label>
                <input
                  type="text"
                  value={settings.openai_base_url}
                  onChange={(e) => setSettings({ ...settings, openai_base_url: e.target.value })}
                  className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                  placeholder="http://localhost:1234/v1"
                />
              </div>

              {/* Write-only. The server never returns a key, so these start
                  empty and only what is typed gets sent. */}
              <div className="rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">API credentials</p>
                <div className="space-y-3">
                  <CredentialField
                    label="OpenAI"
                    field="openai_api_key"
                    configured={settings.openai_api_key_configured}
                    hint={settings.openai_api_key_hint}
                    placeholder="sk-..."
                  />
                  <CredentialField
                    label="Anthropic"
                    field="anthropic_api_key"
                    configured={settings.anthropic_api_key_configured}
                    hint={settings.anthropic_api_key_hint}
                    placeholder="sk-ant-..."
                  />
                  <CredentialField
                    label="Google"
                    field="google_api_key"
                    configured={settings.google_api_key_configured}
                    hint={settings.google_api_key_hint}
                    placeholder="AIza..."
                  />
                </div>
                <p className="text-xs text-text-muted mt-3">
                  Stored encrypted and never shown again. Leave a box blank to keep the
                  stored key; type a single space to remove it and fall back to the
                  deployment&rsquo;s own configuration.
                </p>
              </div>

              {/* The judgement model. Empty name: every stage uses the model above. */}
              <div className="rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                <p className="text-xs font-medium text-text-secondary mb-1 uppercase tracking-wider">Judgement model</p>
                <p className="text-xs text-text-muted mb-3 leading-relaxed">
                  The stages that judge rather than produce - the architect, QA, the reviews,
                  the test rounds and the fixes - run on this model. Leave the name empty to
                  run every stage on the model above. Empty fields below use the model above&rsquo;s.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Model name</label>
                    <input
                      type="text"
                      value={settings.judgement_model_name ?? ''}
                      onChange={(e) => setSettings({ ...settings, judgement_model_name: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                      placeholder="empty: use the model above"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Provider</label>
                    <select
                      value={settings.judgement_provider ?? ''}
                      onChange={(e) => setSettings({ ...settings, judgement_provider: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                    >
                      <option value="">Same as above</option>
                      <option value="local">Local (LM Studio / Ollama)</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="gemini">Google Gemini</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Base URL</label>
                    <input
                      type="text"
                      value={settings.judgement_base_url ?? ''}
                      onChange={(e) => setSettings({ ...settings, judgement_base_url: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                      placeholder="empty: same as above"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Context window (tokens)</label>
                    <input
                      type="number"
                      min={0}
                      step={1000}
                      value={settings.judgement_context_window ?? 0}
                      onChange={(e) => setSettings({ ...settings, judgement_context_window: Number(e.target.value) || 0 })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white tabular-nums focus:outline-none focus:border-primary"
                    />
                  </div>
                </div>
                <div className="mt-3">
                  <CredentialField
                    label="Judgement model key"
                    field="judgement_api_key"
                    configured={settings.judgement_api_key_configured ?? false}
                    hint={settings.judgement_api_key_hint ?? null}
                    placeholder="empty: the key above for its provider"
                  />
                </div>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <span className="text-sm text-primary">{message}</span>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                  <Save className="h-4 w-4" />
                  {saving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      {/* Security */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <Shield className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-white">Security</h2>
        </div>
        <div className="px-6 py-2">
          <InfoRow label="Authentication" value="JWT Bearer Token" />
          <InfoRow label="Token Expiry" value="60 minutes (refresh enabled)" />
          <InfoRow label="Approval Gate" value="Writes and command execution" />
        </div>
      </div>

      {/* About */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <Info className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-white">About</h2>
        </div>
        <div className="px-6 py-2">
          <InfoRow label="Application" value="DevFlow.ai" />
          <InfoRow label="Version" value="0.2.0" />
          <InfoRow label="Backend" value="FastAPI + LangGraph" />
          <InfoRow label="Frontend" value="React + Vite + Tailwind" />
        </div>
      </div>
    </div>
  );
};
