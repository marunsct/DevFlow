// The page's entry point: index.html loads this file as a module.
// Wires the pure logic in tasks.js and the storage adapter in storage.js to the page.
// Sprint 1 scope: add, toggle, counter, empty state, title error, persistence.
// Inline edit and delete arrive in later sprints.
import { create, toggle, filterTasks, generateId, EMPTY_TITLE_MESSAGE } from './tasks.js';
// Note: EMPTY_TITLE_MESSAGE is imported for the sprint 1 wiring; setTitleError receives the error text from create().
import { loadTasks, saveTasks } from './storage.js';

// Module-level state holder, set by init(). Kept here so render() can read it.
let state = null;

// Builds one <li> for a task. Only textContent and setAttribute are used, so
// stored text is never parsed as HTML.
function buildRow(doc, task) {
  const li = doc.createElement('li');
  li.setAttribute('data-id', task.id);

  const main = doc.createElement('div');
  main.className = 'task-row-main';

  const checkbox = doc.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.id = `toggle-${task.id}`;
  checkbox.checked = task.completed === true;

  const label = doc.createElement('label');
  label.htmlFor = `toggle-${task.id}`;
  label.textContent = task.title;
  if (task.completed) label.className = 'completed';

  // The checkbox and its label are wrapped in a div so the stylesheet can lay
  // them out as one row; the label keeps its for= link to the checkbox.
  main.append(checkbox, label);
  li.append(main);

  if (task.description) {
    const desc = doc.createElement('p');
    desc.className = 'description';
    desc.textContent = task.description;
    li.append(desc);
  }

  return li;
}

// Draws the visible list, counter and empty-state text from state. Reads no storage.
export function render() {
  if (!state) return;
  const doc = state.doc;
  const list = doc.getElementById('task-list');
  const visible = filterTasks(state.tasks, state.filter).slice().reverse();

  list.replaceChildren(...visible.map((task) => buildRow(doc, task)));

  const active = state.tasks.filter((task) => task.completed === false).length;
  let counterText;
  if (active === 0) counterText = 'No active tasks left';
  else if (active === 1) counterText = '1 active task left';
  else counterText = `${active} active tasks left`;
  doc.getElementById('counter').textContent = counterText;

  const empty = doc.getElementById('empty-state');
  if (visible.length === 0) {
    let text = 'No tasks yet. Add one above.';
    if (state.filter === 'active') text = 'No active tasks.';
    else if (state.filter === 'completed') text = 'No completed tasks.';
    empty.textContent = text;
    empty.hidden = false;
  } else {
    empty.hidden = true;
  }
}

// Shows or clears the title error under the Title input.
function setTitleError(doc, message) {
  const input = doc.getElementById('title');
  const error = doc.getElementById('title-error');
  if (message) {
    error.textContent = message;
    error.hidden = false;
    input.setAttribute('aria-invalid', 'true');
    input.setAttribute('aria-describedby', 'title-error');
  } else {
    error.hidden = true;
    input.removeAttribute('aria-invalid');
    input.removeAttribute('aria-describedby');
  }
}

// Connects the page to state. Takes the document and storage as arguments so
// it can be run against any page and any Storage-like object.
export function init(documentRef, storageRef) {
  state = {
    tasks: loadTasks(storageRef),
    filter: 'all',
    editingId: null,
    counter: { value: 0 },
    storage: storageRef,
    doc: documentRef,
  };
  const doc = documentRef;

  const addForm = doc.getElementById('add-form');
  if (!addForm) return;

  addForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const titleInput = doc.getElementById('title');
    const descInput = doc.getElementById('description');
    const result = create(state.tasks, titleInput.value, descInput.value, generateId(state.counter));
    if (result.error) {
      setTitleError(doc, result.error);
      titleInput.focus();
      return;
    }
    const saved = saveTasks(state.storage, result.tasks);
    if (saved.ok) {
      state.tasks = result.tasks;
      titleInput.value = '';
      descInput.value = '';
      setTitleError(doc, null);
      doc.getElementById('status').textContent = '';
      titleInput.focus();
    } else {
      doc.getElementById('status').textContent = saved.message;
    }
    render();
  });

  // Clears the title error once the user types a non-blank title.
  doc.getElementById('title').addEventListener('input', (event) => {
    if (event.target.value.trim().length >= 1) setTitleError(doc, null);
  });

  // Checkbox toggle, delegated from the list.
  doc.getElementById('task-list').addEventListener('click', (event) => {
    const target = event.target;
    if (!target || target.type !== 'checkbox' || !target.id.startsWith('toggle-')) return;
    const id = target.id.slice('toggle-'.length);
    if (!state.tasks.some((task) => task.id === id)) {
      render();
      return;
    }
    const next = toggle(state.tasks, id);
    const saved = saveTasks(state.storage, next);
    if (saved.ok) {
      state.tasks = next;
      doc.getElementById('status').textContent = '';
    } else {
      doc.getElementById('status').textContent = saved.message;
    }
    render();
  });

  // Filter radios.
  for (const radio of doc.querySelectorAll('input[name="filter"]')) {
    radio.addEventListener('change', (event) => {
      state.filter = event.target.value;
      render();
    });
  }

  render();
}

// Start only in a browser page. A test that imports this module without a
// document does not run it.
if (typeof document !== 'undefined') {
  init(document, window.localStorage);
}
