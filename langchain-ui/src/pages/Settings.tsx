import React, { useEffect, useState } from 'react';
import { Server, User, Shield, Info, Save } from 'lucide-react';
import { api } from '../api';

import type { SettingsView } from '../types';

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
  openai_api_key?: string;
  anthropic_api_key?: string;
  google_api_key?: string;
}

type CredentialField = 'openai_api_key' | 'anthropic_api_key' | 'google_api_key';

export const Settings: React.FC = () => {
  const [user, setUser] = useState<{ username: string; role?: string } | null>(null);
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  // Held apart from `settings` because these are never read back from the
  // server: an empty box means "leave it alone", not "there is no key".
  const [credentials, setCredentials] = useState<Record<CredentialField, string>>({
    openai_api_key: '',
    anthropic_api_key: '',
    google_api_key: '',
  });

  useEffect(() => {
    api.get('/auth/me').then(res => setUser(res.data)).catch(() => {});
    api.get('/settings').then(res => setSettings(res.data)).catch(() => {});
  }, []);

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
      };
      // Only send a credential the operator actually typed into. An untouched
      // box must not clear a key that is already working.
      (Object.keys(credentials) as CredentialField[]).forEach((field) => {
        if (credentials[field] !== '') form[field] = credentials[field];
      });

      const res = await api.put('/settings', form);
      setSettings(res.data);
      setCredentials({ openai_api_key: '', anthropic_api_key: '', google_api_key: '' });
      setMessage('Settings saved.');
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
