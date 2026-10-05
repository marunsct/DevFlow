import { useEffect, useState, type FormEvent } from 'react';

type Task = { id: number; title: string; description: string; done: boolean };
type Filter = 'all' | 'active' | 'completed';

const KEY = 'tasks';

function loaded(): Task[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]') as Task[];
  } catch {
    return [];
  }
}

export function App() {
  const [tasks, setTasks] = useState<Task[]>(loaded);
  const [filter, setFilter] = useState<Filter>('all');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState('');

  useEffect(() => localStorage.setItem(KEY, JSON.stringify(tasks)), [tasks]);

  const add = (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    setTasks([...tasks, { id: Date.now() + Math.random(), title: title.trim(), description: description.trim(), done: false }]);
    setTitle('');
    setDescription('');
  };
  const change = (id: number, update: Partial<Task>) =>
    setTasks(tasks.map((t) => (t.id === id ? { ...t, ...update } : t)));
  const shown = tasks.filter((t) => filter === 'all' || (filter === 'active' ? !t.done : t.done));

  return (
    <main>
      <form onSubmit={add}>
        <label htmlFor="title">Title</label>
        <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <label htmlFor="description">Description</label>
        <textarea id="description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <button type="submit">Add task</button>
      </form>
      <nav>
        <button onClick={() => setFilter('all')}>All</button>
        <button onClick={() => setFilter('active')}>Active</button>
        <button onClick={() => setFilter('completed')}>Completed</button>
      </nav>
      <ul>
        {shown.map((t) => (
          <li key={t.id}>
            <input id={`done-${t.id}`} type="checkbox" checked={t.done} onChange={(e) => change(t.id, { done: e.target.checked })} />
            <label htmlFor={`done-${t.id}`}>Done</label>
            <span>{`${t.title} ${t.description}`}</span>
            <button onClick={() => { setEditing(t.id); setDraft(t.title); }}>Edit</button>
            <button onClick={() => setTasks(tasks.filter((x) => x.id !== t.id))}>Delete</button>
            {editing === t.id && (
              <>
                <label htmlFor="edit-title">Edit title</label>
                <input id="edit-title" value={draft} onChange={(e) => setDraft(e.target.value)} />
                <button
                  onClick={() => {
                    if (draft.trim()) change(t.id, { title: draft.trim() });
                    setEditing(null);
                  }}
                >
                  Save
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
