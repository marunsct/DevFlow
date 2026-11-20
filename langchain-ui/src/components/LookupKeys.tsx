/**
 * The internet lookup sources' keys (plan WL.3, WL.6): a Stack Exchange key, a GitHub token, the paid web searches
 * (Brave, Tavily) and Context7, all optional.
 *
 * Write-only, as the provider keys on the Settings page are: the page shows a masked hint, a typed value replaces
 * the stored one, and "Remove" deletes it so the deployment's own variable applies again. A key set in the
 * deployment's environment beats one saved here, and the page says so.
 */
import React, { useEffect, useState } from 'react';
import { KeyRound } from 'lucide-react';
import { api } from '../api';
import { useFeedback } from '../ui';

export interface LookupKeysView {
  stackexchange_key_hint: string | null;
  stackexchange_key_configured: boolean;
  stackexchange_key_from_environment: boolean;
  github_token_hint: string | null;
  github_token_configured: boolean;
  github_token_from_environment: boolean;
  brave_api_key_hint?: string | null;
  brave_api_key_configured?: boolean;
  brave_api_key_from_environment?: boolean;
  tavily_api_key_hint?: string | null;
  tavily_api_key_configured?: boolean;
  tavily_api_key_from_environment?: boolean;
  context7_api_key_hint?: string | null;
  context7_api_key_configured?: boolean;
  context7_api_key_from_environment?: boolean;
}

type Key = 'stackexchange_key' | 'github_token' | 'brave_api_key' | 'tavily_api_key' | 'context7_api_key';

const KEYS: Array<[Key, string, string]> = [
  ['stackexchange_key', 'Stack Exchange key',
    'A free Stack Apps key raises Stack Exchange\'s limit from 300 lookups a day to 10,000.'],
  ['github_token', 'GitHub token',
    'A token with no scopes raises the GitHub issue search\'s limit. Never sent anywhere but GitHub.'],
  ['brave_api_key', 'Brave Search key',
    'Paid web search, asked only when the free sources found fewer than two answers, within a daily request cap.'],
  ['tavily_api_key', 'Tavily key',
    'Paid web search, asked after Brave on the same terms.'],
  ['context7_api_key', 'Context7 key',
    'Library documentation by version. Asked without a key at a lower limit; a key raises it.'],
];

const EMPTY: Record<Key, string> = {
  stackexchange_key: '', github_token: '', brave_api_key: '', tavily_api_key: '', context7_api_key: '',
};

const isView = (data: unknown): data is LookupKeysView =>
  !!data && typeof data === 'object' && !Array.isArray(data) && 'github_token_configured' in data;

export const LookupKeys: React.FC<{ isAdmin: boolean }> = ({ isAdmin }) => {
  const [view, setView] = useState<LookupKeysView | null>(null);
  const [typed, setTyped] = useState<Record<Key, string>>(EMPTY);
  const [busy, setBusy] = useState(false);
  const { notify } = useFeedback();

  useEffect(() => {
    api.get('/settings/lookup-keys').then((res) => isView(res.data) && setView(res.data)).catch(() => setView(null));
  }, []);

  const save = async (values: Partial<Record<Key, string>>) => {
    setBusy(true);
    try {
      const res = await api.put('/settings/lookup-keys', values);
      if (isView(res.data)) setView(res.data);
      setTyped(EMPTY);
      notify('Saved.');
    } catch (err: any) {
      notify(err.response?.data?.detail ?? 'Only an administrator can change a key.');
    } finally {
      setBusy(false);
    }
  };

  const entered = Object.fromEntries(Object.entries(typed).filter(([, value]) => value.trim())) as Partial<Record<Key, string>>;

  return (
    <section className="glass-card rounded-2xl overflow-hidden" aria-labelledby="lookup-keys-heading">
      <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
        <KeyRound className="h-5 w-5 text-primary" />
        <h2 id="lookup-keys-heading" className="font-semibold text-text-primary">Internet lookup keys</h2>
      </div>
      <div className="px-6 py-4 space-y-4">
        <p className="text-sm text-text-secondary">
          Optional. Without them the lookups still work, at the sources' lower free limits. Stored encrypted, shown
          only as their last characters, and never given to a model or a sandbox.
        </p>
        {KEYS.map(([key, label, hint]) => {
          const hinted = view?.[`${key}_hint` as const];
          const fromEnvironment = view?.[`${key}_from_environment` as const];
          return (
            <div key={key} className="space-y-1">
              <label htmlFor={`lookup-${key}`} className="block text-sm font-medium text-text-primary">{label}</label>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <input
                  id={`lookup-${key}`}
                  type="password"
                  autoComplete="off"
                  maxLength={512}
                  value={typed[key]}
                  disabled={!isAdmin || busy}
                  placeholder={hinted ?? 'not set'}
                  onChange={(e) => setTyped({ ...typed, [key]: e.target.value })}
                  className="w-full sm:max-w-sm rounded-lg border border-border bg-transparent px-3 py-2 text-sm text-text-primary disabled:opacity-60"
                />
                {isAdmin && hinted && !fromEnvironment && (
                  <button type="button" disabled={busy} onClick={() => save({ [key]: '' })}
                    className="self-start rounded-lg border border-border px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary">
                    Remove
                  </button>
                )}
              </div>
              <p className="text-xs text-text-muted">
                {hint}
                {fromEnvironment && ' Set in the deployment\'s environment, which beats a key saved here.'}
              </p>
            </div>
          );
        })}
        {isAdmin && (
          <button type="button" disabled={busy || Object.keys(entered).length === 0} onClick={() => save(entered)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
            Save keys
          </button>
        )}
      </div>
    </section>
  );
};
