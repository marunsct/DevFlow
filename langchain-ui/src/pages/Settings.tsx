import React, { useEffect, useState } from 'react';
import { Server, User, Shield, Info, Save, Trash2 } from 'lucide-react';
import { api, saveLocalModelSettings, saveFrontierModelSettings } from '../api';

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
  judgement_max_output_tokens: number;
  judgement_api_key?: string;
  escalate_after_attempts: number;
  plan_on_judgement_model: boolean;
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
  const [savingLocal, setSavingLocal] = useState(false);
  const [savingFrontier, setSavingFrontier] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [detectNote, setDetectNote] = useState('');
  const [message, setMessage] = useState('');

  // Separated saved model profiles for build (local) and frontier models
  const [localProfiles, setLocalProfiles] = useState<ModelProfile[]>([]);
  const [frontierProfiles, setFrontierProfiles] = useState<ModelProfile[]>([]);
  const [chosenLocalProfile, setChosenLocalProfile] = useState('');
  const [chosenFrontierProfile, setChosenFrontierProfile] = useState('');

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
    api.get<ModelProfile[]>('/settings/models?target=build')
      .then(res => setLocalProfiles(res.data))
      .catch(() => {});
    api.get<ModelProfile[]>('/settings/models?target=frontier')
      .then(res => setFrontierProfiles(res.data))
      .catch(() => {});
  };

  /** Fill the build model form from a saved local model. */
  const applyLocalProfile = (id: string) => {
    setChosenLocalProfile(id);
    const profile = localProfiles.find(p => p.id === id);
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
    setMessage('Filled local model fields from saved profile. Click "Save Local Model" to apply.');
  };

  /** Fill or clear the frontier model form from a saved frontier profile or No Model. */
  const applyFrontierProfile = (id: string) => {
    setChosenFrontierProfile(id);
    if (!settings) return;
    if (id === '__none__') {
      setSettings({
        ...settings,
        judgement_provider: '',
        judgement_base_url: '',
        judgement_model_name: '',
        judgement_context_window: 0,
        judgement_max_output_tokens: 0,
      });
      setMessage('Selected "No model" for frontier. Click "Save Frontier Model" to apply.');
      return;
    }
    const profile = frontierProfiles.find(p => p.id === id);
    if (!profile) return;
    setSettings({
      ...settings,
      judgement_provider: profile.judgement_provider ?? settings.judgement_provider,
      judgement_base_url: profile.judgement_base_url ?? settings.judgement_base_url,
      judgement_model_name: profile.judgement_model_name ?? settings.judgement_model_name,
      judgement_context_window: profile.judgement_context_window ?? settings.judgement_context_window,
      judgement_max_output_tokens: profile.judgement_max_output_tokens ?? settings.judgement_max_output_tokens,
      escalate_after_attempts: profile.escalate_after_attempts ?? settings.escalate_after_attempts,
      plan_on_judgement_model: profile.plan_on_judgement_model ?? settings.plan_on_judgement_model,
    });
    setMessage('Filled frontier model fields from saved profile. Click "Save Frontier Model" to apply.');
  };

  /** Explicitly set Frontier Model to No Model (clearing its settings). */
  const selectNoFrontierModel = () => {
    if (!settings) return;
    setChosenFrontierProfile('__none__');
    setSettings({
      ...settings,
      judgement_provider: '',
      judgement_base_url: '',
      judgement_model_name: '',
      judgement_context_window: 0,
      judgement_max_output_tokens: 0,
    });
    setMessage('Frontier model cleared (No model selected). Click "Save Frontier Model" to apply.');
  };

  const forgetLocalProfile = async () => {
    if (!chosenLocalProfile) return;
    try {
      await api.delete(`/settings/models/${chosenLocalProfile}`);
      setChosenLocalProfile('');
      loadProfiles();
      setMessage('Saved local model removed.');
    } catch (err: any) {
      setMessage(err.response?.data?.detail ?? 'Could not remove the saved model.');
    }
  };

  const forgetFrontierProfile = async () => {
    if (!chosenFrontierProfile || chosenFrontierProfile === '__none__') return;
    try {
      await api.delete(`/settings/models/${chosenFrontierProfile}`);
      setChosenFrontierProfile('');
      loadProfiles();
      setMessage('Saved frontier model removed.');
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
        className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary font-mono focus:outline-none focus:border-primary"
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
        judgement_max_output_tokens: settings.judgement_max_output_tokens ?? 0,
        escalate_after_attempts: settings.escalate_after_attempts ?? 2,
        plan_on_judgement_model: settings.plan_on_judgement_model ?? true,
      };
      // Only send a credential the operator actually typed into. An untouched
      // box must not clear a key that is already working.
      (Object.keys(credentials) as CredentialField[]).forEach((field) => {
        if (credentials[field] !== '') form[field] = credentials[field];
      });

      const res = await api.put('/settings', form);
      setSettings(res.data);
      setCredentials({ openai_api_key: '', anthropic_api_key: '', google_api_key: '', judgement_api_key: '' });
      setMessage('Settings saved.');
      setChosenLocalProfile('');
      setChosenFrontierProfile('');
      loadProfiles();
    } catch (err: any) {
      setMessage(err.response?.data?.detail ?? 'Could not save settings.');
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(''), 3000);
    }
  };

  /** Save only the local build model settings and add to saved local models. */
  const handleSaveLocal = async () => {
    if (!settings) return;
    setSavingLocal(true);
    setMessage('');
    try {
      const payload = {
        llm_provider: settings.llm_provider,
        openai_base_url: settings.openai_base_url,
        model_name: settings.model_name,
        model_context_window: settings.model_context_window,
        model_max_output_tokens: settings.model_max_output_tokens ?? 0,
        thinking_mode: settings.thinking_mode ?? 'default',
        thinking_effort: settings.thinking_effort ?? 'medium',
        ...(credentials[buildKeyField] !== '' ? { api_key: credentials[buildKeyField] } : {}),
      };
      const res = await saveLocalModelSettings(payload);
      setSettings(res);
      setCredentials(prev => ({ ...prev, [buildKeyField]: '' }));
      setMessage('Local build model saved and added to saved local models.');
      setChosenLocalProfile('');
      loadProfiles();
    } catch (err: any) {
      setMessage(err.response?.data?.detail ?? 'Could not save local model settings.');
    } finally {
      setSavingLocal(false);
      setTimeout(() => setMessage(''), 4000);
    }
  };

  /** Save only the frontier model settings, or explicitly disable it with No Model. */
  const handleSaveFrontier = async () => {
    if (!settings) return;
    setSavingFrontier(true);
    setMessage('');
    try {
      const isNoModel = chosenFrontierProfile === '__none__' || !settings.judgement_model_name?.trim();
      const payload = {
        judgement_provider: settings.judgement_provider ?? '',
        judgement_base_url: settings.judgement_base_url ?? '',
        judgement_model_name: settings.judgement_model_name ?? '',
        judgement_context_window: settings.judgement_context_window ?? 0,
        judgement_max_output_tokens: settings.judgement_max_output_tokens ?? 0,
        escalate_after_attempts: settings.escalate_after_attempts ?? 2,
        plan_on_judgement_model: settings.plan_on_judgement_model ?? true,
        no_model: isNoModel,
        ...(credentials.judgement_api_key !== '' ? { judgement_api_key: credentials.judgement_api_key } : {}),
      };
      const res = await saveFrontierModelSettings(payload);
      setSettings(res);
      setCredentials(prev => ({ ...prev, judgement_api_key: '' }));
      if (isNoModel) {
        setMessage('Frontier model disabled. All operations will use local build model.');
      } else {
        setMessage('Frontier model saved and added to saved frontier models.');
      }
      loadProfiles();
    } catch (err: any) {
      setMessage(err.response?.data?.detail ?? 'Could not save frontier model settings.');
    } finally {
      setSavingFrontier(false);
      setTimeout(() => setMessage(''), 4000);
    }
  };

  // The one key box for the build model: the credential its provider reads.
  const buildProvider = (settings?.llm_provider ?? 'local').toLowerCase();
  const buildKeyField: CredentialField =
    buildProvider === 'anthropic' ? 'anthropic_api_key'
      : buildProvider === 'gemini' || buildProvider === 'google' ? 'google_api_key'
        : 'openai_api_key';
  const buildKeyLabel =
    buildKeyField === 'anthropic_api_key' ? 'Anthropic key'
      : buildKeyField === 'google_api_key' ? 'Google key' : 'API key';
  const buildKeyConfigured = Boolean(settings?.[`${buildKeyField}_configured` as keyof typeof settings]);
  const buildKeyHint = (settings?.[`${buildKeyField}_hint` as keyof typeof settings] as string | null | undefined) ?? null;

  return (
    <div className="w-full mt-4 space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl font-bold text-text-primary mb-1">Settings</h1>
        <p className="text-text-secondary text-sm">View system configuration and account details.</p>
      </div>

      {/* Wide screens: the models on the left, the account and the rest beside them. */}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-6 items-start">
      <div className="space-y-6 min-w-0">
      {/* Server Configuration */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <Server className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-text-primary">AI Provider Configuration</h2>
        </div>
        <div className="px-6 py-4">
          {!settings ? (
            <p className="text-sm text-text-muted">Loading settings...</p>
          ) : (
            <form onSubmit={handleSave} className="space-y-4">
              <div className="rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                <div className="flex items-center justify-between mb-1">
                  <label
                    htmlFor="saved-local-models"
                    className="block text-sm font-medium text-text-secondary"
                  >
                    Saved Local (Build) Models
                  </label>
                  <button
                    type="button"
                    onClick={handleSaveLocal}
                    disabled={savingLocal}
                    className="flex items-center gap-1.5 px-3 py-1 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/40 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {savingLocal ? 'Saving Local...' : 'Save Local Model'}
                  </button>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <select
                    id="saved-local-models"
                    aria-label="Saved local models"
                    value={chosenLocalProfile}
                    onChange={(e) => applyLocalProfile(e.target.value)}
                    className="flex-1 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                  >
                    <option value="">Choose a saved local model...</option>
                    {localProfiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                        {p.model_context_window ? ` - ${p.model_context_window.toLocaleString()} tokens` : ''}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={forgetLocalProfile}
                    disabled={!chosenLocalProfile}
                    title="Remove this saved local model"
                    aria-label="Remove this saved local model"
                    className="rounded-lg border border-border/50 p-2 text-text-secondary hover:text-text-primary hover:border-primary/50 disabled:opacity-40 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <p className="mt-1.5 text-xs text-text-muted leading-relaxed">
                  Saved configurations for your local build model (LM Studio / Ollama / local endpoints).
                  Click &ldquo;Save Local Model&rdquo; to persist current build model settings separately.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">Provider</label>
                <select aria-label="Provider"
                  value={settings.llm_provider}
                  onChange={(e) => setSettings({ ...settings, llm_provider: e.target.value })}
                  className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                >
                  <option value="local">Local (LM Studio / Ollama)</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">Model Name</label>
                <input aria-label="Model Name"
                  type="text"
                  value={settings.model_name}
                  onChange={(e) => setSettings({ ...settings, model_name: e.target.value })}
                  className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                  placeholder="e.g. gpt-4o, claude-3-5-sonnet-20241022"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">
                  Context window
                </label>
                <div className="flex items-center gap-2">
                  <input aria-label="Context window"
                    type="number"
                    min={32000}
                    step={1000}
                    value={settings.model_context_window}
                    onChange={(e) =>
                      setSettings({ ...settings, model_context_window: Number(e.target.value) || 0 })
                    }
                    className="w-40 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary tabular-nums focus:outline-none focus:border-primary"
                  />
                  <span className="text-xs text-text-muted">tokens</span>
                  <button
                    type="button"
                    onClick={detectWindow}
                    disabled={detecting}
                    className="ml-auto rounded-lg border border-border/50 px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:border-primary/50 disabled:opacity-50 transition-colors"
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
                      className="w-40 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary tabular-nums focus:outline-none focus:border-primary"
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
                    className="w-64 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
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
                          className="w-40 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
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
                <input aria-label="Base URL"
                  type="text"
                  value={settings.openai_base_url}
                  onChange={(e) => setSettings({ ...settings, openai_base_url: e.target.value })}
                  className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                  placeholder="http://localhost:1234/v1"
                />
              </div>

              {/* Write-only. The server never returns a key, so this starts empty
                  and only what is typed gets sent. Each endpoint keeps its own. */}
              <div className="rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                <p className="text-xs font-medium text-text-secondary mb-1 uppercase tracking-wider">API key for this endpoint</p>
                <p className="text-xs text-text-muted mb-3 leading-relaxed">
                  Kept for the provider and address above: each endpoint remembers its own key, so
                  switching to a saved model uses the key saved with it.{' '}
                  {settings.endpoint_key_saved
                    ? 'This endpoint has a key saved.'
                    : 'No key is saved for this endpoint yet.'}
                </p>
                <CredentialField
                  label={buildKeyLabel}
                  field={buildKeyField}
                  configured={buildKeyConfigured}
                  hint={buildKeyHint}
                  placeholder="leave empty to keep the saved key"
                />
              </div>

              {/* The planning and judgement model. Empty name: every stage uses the model above. */}
              <div className="rounded-lg border border-border/50 bg-surface/30 px-3 py-3">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                    Planning &amp; judgement model (frontier)
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={selectNoFrontierModel}
                      className="px-2.5 py-1 bg-surface/60 hover:bg-surface border border-border/70 rounded-lg text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
                    >
                      Select No Model
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveFrontier}
                      disabled={savingFrontier}
                      className="flex items-center gap-1.5 px-3 py-1 bg-primary/20 hover:bg-primary/30 text-primary border border-primary/40 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      <Save className="h-3.5 w-3.5" />
                      {savingFrontier ? 'Saving Frontier...' : 'Save Frontier Model'}
                    </button>
                  </div>
                </div>
                <p className="text-xs text-text-muted mb-3 leading-relaxed">
                  The model above is the <strong>build model</strong>: it writes the code and the fixes.
                  This one writes the plan and the specification, writes and reviews the acceptance
                  tests, triages the test rounds and runs the reviews - and takes over any work order
                  or defect the build model failed. <strong>Select &ldquo;No model&rdquo;</strong> to disable all
                  frontier calls and run every stage on the build model above.
                </p>

                {/* Saved frontier models dropdown */}
                <div className="mb-4 p-2.5 rounded-lg border border-border/40 bg-surface/20">
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="saved-frontier-models" className="block text-xs font-medium text-text-secondary">
                      Saved Frontier Models
                    </label>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <select
                      id="saved-frontier-models"
                      value={chosenFrontierProfile}
                      onChange={(e) => applyFrontierProfile(e.target.value)}
                      className="flex-1 bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                    >
                      <option value="">Choose a saved frontier model...</option>
                      <option value="__none__">🚫 No model (use local model only)</option>
                      {frontierProfiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label} {p.judgement_model_name ? `(${p.judgement_model_name})` : ''}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={forgetFrontierProfile}
                      disabled={!chosenFrontierProfile || chosenFrontierProfile === '__none__'}
                      title="Remove this saved frontier model"
                      aria-label="Remove this saved frontier model"
                      className="rounded-lg border border-border/50 p-2 text-text-secondary hover:text-text-primary hover:border-primary/50 disabled:opacity-40 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {(!settings.judgement_model_name?.trim() || chosenFrontierProfile === '__none__') && (
                  <div className="mb-3 px-3 py-2 rounded-lg bg-surface/40 border border-border/40 text-xs text-primary flex items-center gap-2">
                    <span>⚡ Frontier model is currently <strong>disabled</strong>: all tasks run on the local build model only.</span>
                  </div>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Model name</label>
                    <input aria-label="Model name"
                      type="text"
                      value={settings.judgement_model_name ?? ''}
                      onChange={(e) => setSettings({ ...settings, judgement_model_name: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                      placeholder="empty: use the model above"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Provider</label>
                    <select aria-label="Provider"
                      value={settings.judgement_provider ?? ''}
                      onChange={(e) => setSettings({ ...settings, judgement_provider: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
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
                    <input aria-label="Base URL"
                      type="text"
                      value={settings.judgement_base_url ?? ''}
                      onChange={(e) => setSettings({ ...settings, judgement_base_url: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                      placeholder="empty: same server, or the provider's own"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Context window (tokens)</label>
                    <input aria-label="Context window (tokens)"
                      type="number"
                      min={0}
                      step={1000}
                      value={settings.judgement_context_window ?? 0}
                      onChange={(e) => setSettings({ ...settings, judgement_context_window: Number(e.target.value) || 0 })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary tabular-nums focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-text-secondary mb-1">Longest reply (tokens)</label>
                    <input aria-label="Longest reply (tokens)"
                      type="number"
                      min={0}
                      step={1000}
                      value={settings.judgement_max_output_tokens ?? 0}
                      onChange={(e) => setSettings({ ...settings, judgement_max_output_tokens: Number(e.target.value) || 0 })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary tabular-nums focus:outline-none focus:border-primary"
                      placeholder="0: derived from its window"
                    />
                  </div>
                </div>
                <div className="mt-3">
                  <CredentialField
                    label="API key for this model's endpoint"
                    field="judgement_api_key"
                    configured={settings.judgement_api_key_configured ?? false}
                    hint={settings.judgement_api_key_hint ?? null}
                    placeholder="leave empty to keep the saved key"
                  />
                  <p className="text-xs text-text-muted mt-1">
                    {settings.judgement_endpoint_key_saved
                      ? 'This endpoint has a key saved.'
                      : 'No key is saved for this endpoint yet: the key above is used if the endpoint is the same.'}
                  </p>
                </div>
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="escalate-after" className="block text-xs text-text-secondary mb-1">
                      Escalate after failed tries on the build model
                    </label>
                    <input
                      id="escalate-after"
                      type="number"
                      min={1}
                      max={10}
                      value={settings.escalate_after_attempts ?? 2}
                      onChange={(e) => setSettings({ ...settings, escalate_after_attempts: Math.max(1, Number(e.target.value) || 2) })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                    />
                    <p className="text-xs text-text-muted mt-1">
                      A work order that had to start over, or a defect whose fixes failed, this many
                      times goes to this model. If it fails here too, the run goes on as before.
                    </p>
                  </div>
                  <label className="flex items-start gap-2 text-sm text-text-secondary sm:mt-5">
                    <input
                      type="checkbox"
                      checked={settings.plan_on_judgement_model ?? true}
                      onChange={(e) => setSettings({ ...settings, plan_on_judgement_model: e.target.checked })}
                      className="mt-0.5"
                    />
                    <span>
                      Plan on this model
                      <span className="block text-xs text-text-muted">
                        Intake, stack choice, sprint plan and work orders. Off: they run on the build model.
                      </span>
                    </span>
                  </label>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <span className="text-sm text-primary">{message}</span>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-primary-foreground rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                  <Save className="h-4 w-4" />
                  {saving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      </div>
      <div className="space-y-6 min-w-0">
      {/* Account */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <User className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-text-primary">Account</h2>
        </div>
        <div className="px-6 py-2">
          <InfoRow label="Username" value={user?.username || 'Loading...'} />
          <InfoRow label="Role" value={user?.role ?? "-"} />
          <InfoRow label="Session" value="Active" />
        </div>
      </div>

      {/* Security */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
          <Shield className="h-5 w-5 text-primary" />
          <h2 className="font-semibold text-text-primary">Security</h2>
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
          <h2 className="font-semibold text-text-primary">About</h2>
        </div>
        <div className="px-6 py-2">
          <InfoRow label="Application" value="DevFlow.ai" />
          <InfoRow label="Version" value="0.2.0" />
          <InfoRow label="Backend" value="FastAPI + LangGraph" />
          <InfoRow label="Frontend" value="React + Vite + Tailwind" />
        </div>
      </div>
      </div>
      </div>
    </div>
  );
};
