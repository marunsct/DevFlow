const KEY = 'tasks';
let tasks = JSON.parse(localStorage.getItem(KEY) || '[]');
let filter = 'all';
let editing = null;
const save = () => localStorage.setItem(KEY, JSON.stringify(tasks));
const list = document.getElementById('list');

function render() {
  list.innerHTML = '';
  tasks
    .filter((t) => filter === 'all' || (filter === 'active' ? !t.done : t.done))
    .forEach((t) => {
      const li = document.createElement('li');
      const done = document.createElement('input');
      done.type = 'checkbox'; done.checked = t.done; done.id = `done-${t.id}`;
      const doneLabel = document.createElement('label');
      doneLabel.htmlFor = done.id; doneLabel.textContent = 'Done';
      done.addEventListener('change', () => { t.done = done.checked; save(); render(); });
      const text = document.createElement('span');
      text.textContent = `${t.title} ${t.description}`;
      const edit = document.createElement('button'); edit.textContent = 'Edit';
      edit.addEventListener('click', () => { editing = t.id; render(); });
      const del = document.createElement('button'); del.textContent = 'Delete';
      del.addEventListener('click', () => { tasks = tasks.filter((x) => x.id !== t.id); save(); render(); });
      li.append(done, doneLabel, text, edit, del);
      if (editing === t.id) {
        const field = document.createElement('input'); field.id = 'edit-title'; field.value = t.title;
        const label = document.createElement('label'); label.htmlFor = 'edit-title'; label.textContent = 'Edit title';
        const ok = document.createElement('button'); ok.textContent = 'Save';
        ok.addEventListener('click', () => { if (field.value.trim()) { t.title = field.value.trim(); save(); } editing = null; render(); });
        li.append(label, field, ok);
      }
      list.append(li);
    });
}

document.getElementById('add').addEventListener('submit', (event) => {
  event.preventDefault();
  const title = document.getElementById('title').value.trim();
  if (!title) return;
  tasks.push({ id: Date.now() + Math.random(), title, description: document.getElementById('description').value.trim(), done: false });
  save(); event.target.reset(); render();
});
document.querySelectorAll('[data-filter]').forEach((b) => b.addEventListener('click', () => { filter = b.dataset.filter; render(); }));
render();
