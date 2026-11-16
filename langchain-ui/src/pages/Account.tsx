import { useEffect, useState } from 'react';
import { api } from '../api';

type Person = { username: string; role: string; disabled: boolean };

/** Your account, and - for an administrator - everyone's (LR.36). Accounts were made only from the command line. */
export function Account() {
  const [current, setCurrent] = useState('');
  const [fresh, setFresh] = useState('');
  const [said, setSaid] = useState('');
  const [people, setPeople] = useState<Person[] | null>(null);
  const [newName, setNewName] = useState('');
  const [newRole, setNewRole] = useState('operator');
  const [made, setMade] = useState('');

  const load = () => api.get<Person[]>('/users').then((r) => setPeople(r.data)).catch(() => setPeople(null));
  useEffect(() => { void load(); }, []);

  const change = async () => {
    try {
      await api.post('/auth/password', { current_password: current, new_password: fresh });
      setSaid('Password changed.'); setCurrent(''); setFresh('');
    } catch (err: any) {
      setSaid(err.response?.status === 422 ? 'The new password needs at least 12 characters.' : err.response?.data?.detail ?? 'Could not change it.');
    }
  };
  const add = async () => {
    try {
      const r = await api.post<{ username: string; password?: string }>('/users', { username: newName, role: newRole });
      setMade(r.data.password ? `${r.data.username}'s password, shown once: ${r.data.password}` : `${r.data.username} added.`);
      setNewName(''); void load();
    } catch (err: any) {
      setMade(err.response?.data?.detail ?? 'Could not add them.');
    }
  };
  const toggle = async (person: Person) => {
    await api.patch(`/users/${person.username}`, { disabled: !person.disabled }).catch(() => undefined);
    void load();
  };

  const field = 'bg-surface border border-border rounded-lg px-3 py-1.5 text-sm text-text-primary';
  return (
    <div className="max-w-2xl space-y-8">
      <section>
        <h1 className="text-2xl font-bold text-text-primary">Account</h1>
        <h2 className="mt-4 text-sm font-semibold text-text-primary">Change your password</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          <input type="password" aria-label="Current password" placeholder="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} className={field} />
          <input type="password" aria-label="New password" placeholder="New password (12+ characters)" value={fresh} onChange={(e) => setFresh(e.target.value)} className={field} />
          <button onClick={change} disabled={!current || !fresh} className="rounded-lg border border-primary/40 px-3 py-1.5 text-sm text-primary disabled:opacity-50">Change it</button>
        </div>
        {said && <p className="mt-2 text-sm text-text-secondary" role="status">{said}</p>}
      </section>
      {people && (
        <section data-testid="people">
          <h2 className="text-sm font-semibold text-text-primary">People</h2>
          <ul className="mt-2 divide-y divide-border rounded-xl border border-border">
            {people.map((person) => (
              <li key={person.username} className="flex items-center justify-between px-3 py-2 text-sm">
                <span className="text-text-primary">{person.username} <span className="text-text-muted">{person.role}{person.disabled ? ', disabled' : ''}</span></span>
                <button onClick={() => void toggle(person)} className="text-xs text-text-secondary underline">{person.disabled ? 'Enable' : 'Disable'}</button>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <input aria-label="New person's name" placeholder="Name" value={newName} onChange={(e) => setNewName(e.target.value)} className={field} />
            <select aria-label="Their role" value={newRole} onChange={(e) => setNewRole(e.target.value)} className={field}>
              <option value="operator">operator: starts and steers runs</option>
              <option value="viewer">viewer: reads only</option>
              <option value="admin">admin: settings and people too</option>
            </select>
            <button onClick={add} disabled={!newName} className="rounded-lg border border-primary/40 px-3 py-1.5 text-sm text-primary disabled:opacity-50">Add</button>
          </div>
          {made && <p className="mt-2 text-sm text-text-secondary" role="status">{made}</p>}
        </section>
      )}
    </div>
  );
}
