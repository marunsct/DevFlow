import React, { useEffect, useState } from 'react';
import { Server, User, Shield, Info, Save } from 'lucide-react';
import { api } from '../api';

interface SettingsPayload {
  llm_provider: string;
  openai_base_url: string;
  openai_api_key: string;
  anthropic_api_key?: string;
  google_api_key?: string;
  model_name: string;
}

export const Settings: React.FC = () => {
  const [user, setUser] = useState<{ username: string } | null>(null);
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    api.get('/auth/me').then(res => setUser(res.data)).catch(() => {});
    api.get('/settings').then(res => setSettings(res.data)).catch(() => {});
  }, []);

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
      const res = await api.put('/settings', settings);
      setSettings(res.data);
      setMessage('Settings saved successfully!');
    } catch (err: any) {
      setMessage('Failed to save settings.');
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
          <InfoRow label="Role" value="Administrator" />
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

              {(settings.llm_provider === 'local' || settings.llm_provider === 'openai') && (
                <>
                  {settings.llm_provider === 'local' && (
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
                  )}
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-1">OpenAI API Key</label>
                    <input
                      type="password"
                      value={settings.openai_api_key}
                      onChange={(e) => setSettings({ ...settings, openai_api_key: e.target.value })}
                      className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                    />
                  </div>
                </>
              )}

              {settings.llm_provider === 'anthropic' && (
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1">Anthropic API Key</label>
                  <input
                    type="password"
                    value={settings.anthropic_api_key || ''}
                    onChange={(e) => setSettings({ ...settings, anthropic_api_key: e.target.value })}
                    className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                  />
                </div>
              )}

              {settings.llm_provider === 'gemini' && (
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1">Google API Key</label>
                  <input
                    type="password"
                    value={settings.google_api_key || ''}
                    onChange={(e) => setSettings({ ...settings, google_api_key: e.target.value })}
                    className="w-full bg-surface/50 border border-border/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                  />
                </div>
              )}

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
          <InfoRow label="Token Expiry" value="24 hours" />
          <InfoRow label="Approval Gate" value="Enabled (per-file)" />
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
          <InfoRow label="Version" value="0.1.0" />
          <InfoRow label="Backend" value="FastAPI + LangGraph" />
          <InfoRow label="Frontend" value="React + Vite + Tailwind" />
        </div>
      </div>
    </div>
  );
};
