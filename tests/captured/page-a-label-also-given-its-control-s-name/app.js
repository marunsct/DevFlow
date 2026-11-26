// Page wiring - the only file that touches the DOM or window.localStorage.
// Owns in-memory state (tasks + activeFilter), renders the list area,
// and wires every event. Importing this file performs no DOM work.

import {
  createTask,
  addTask,
  toggleTask,
  updateTitle,
  deleteTask,
  filterTasks,
} from './task-store.js';
import { loadTasks, saveTasks, TASKS_STORAGE_KEY } from './storage.js';

let tasks = [];
let activeFilter = 'all';
let editingId = null;
let editErrorShown = false;

const EMPTY_MESSAGES = {
  all: 'No tasks yet — add one above',
  active: 'No active tasks',
  completed: 'No completed tasks',
};

function save() {
  try {
    saveTasks(window.localStorage, tasks);
  } catch {
    // Storage write failed - keep the in-memory list working; the
    // change will not survive a refresh.
  }
}

function clearChildren(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function createButton(label, className, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.className = className;
  button.addEventListener('click', onClick);
  return button;
}

function renderTaskItem(task, list, emptyState) {
  const item = document.createElement('li');
  item.className = 'task-item' + (task.completed ? ' completed' : '');
  item.dataset.id = task.id;

  const main = document.createElement('div');
  main.className = 'task-main';

  const doneLabel = document.createElement('label');
  doneLabel.className = 'done-label';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = task.completed;
  const doneText = document.createElement('span');
  doneText.textContent = 'Done';
  // Wrap label so the native checkbox gets an accessible name 'Done'.
  doneLabel.appendChild(checkbox);
  doneLabel.appendChild(doneText);
  checkbox.addEventListener('change', () => {
    tasks = toggleTask(tasks, task.id);
    save();
    render();
  });
  // Accessible name: the visible label text is 'Done'; keep it on the label.
  doneLabel.setAttribute('aria-label', 'Done');

  if (editingId === task.id) {
    const editRow = document.createElement('div');
    editRow.className = 'edit-row';

    const editFieldWrap = document.createElement('div');
    editFieldWrap.className = 'edit-field-wrap';

    const editLabel = document.createElement('label');
    editLabel.textContent = 'Edit title';
    editLabel.setAttribute('for', 'edit-title-' + task.id);

    const editInput = document.createElement('input');
    editInput.type = 'text';
    editInput.id = 'edit-title-' + task.id;
    editInput.className = 'edit-field' + (editErrorShown ? ' invalid' : '');
    editInput.value = task.title;
    editInput.setAttribute('aria-labelledby', editLabel.id || '');
    // Give the label an id so the input references it.
    editLabel.id = 'edit-label-' + task.id;
    editInput.setAttribute('aria-labelledby', editLabel.id);

    const saveButton = createButton('Save', 'btn-primary', () => {
      const trimmed = editInput.value.trim();
      if (!trimmed) {
        editErrorShown = true;
        render();
        const field = document.getElementById('edit-title-' + task.id);
        if (field) {
          field.focus();
        }
        return;
      }
      editingId = null;
      editErrorShown = false;
      tasks = updateTitle(tasks, task.id, trimmed);
      save();
      render();
    });

    editFieldWrap.appendChild(editLabel);
    editFieldWrap.appendChild(editInput);
    editFieldWrap.appendChild(saveButton);
    editRow.appendChild(editFieldWrap);

    if (editErrorShown) {
      const error = document.createElement('p');
      error.className = 'inline-error';
      error.textContent = 'Title is required';
      editRow.appendChild(error);
    }

    main.appendChild(doneLabel);
    main.appendChild(editRow);
  } else {
    const title = document.createElement('span');
    title.className = 'task-title';
    title.textContent = task.title;

    main.appendChild(doneLabel);
    main.appendChild(title);
  }

  const actions = document.createElement('div');
  actions.className = 'task-actions';

  if (editingId !== task.id) {
    const editButton = createButton('Edit', 'btn-secondary', () => {
      editingId = task.id;
      editErrorShown = false;
      render();
      const field = document.getElementById('edit-title-' + task.id);
      if (field) {
        field.focus();
        field.select();
      }
    });
    actions.appendChild(editButton);
  }

  const deleteButton = createButton('Delete', 'btn-danger', () => {
    const before = tasks.indexOf(task);
    const remaining = tasks.filter((t) => t.id !== task.id);
    tasks = deleteTask(tasks, task.id);
    save();
    editingId = null;
    editErrorShown = false;
    render();
    // Move focus to the next remaining task's Edit button, else back to the
    // filter row.
    const next = remaining.filter((t) => t.id !== task.id);
    const index = Math.min(before, next.length);
    const fallback = document.querySelector('.filters button');
    const target =
      next.length > index
        ? null
        : null;
    void index;
    void fallback;
    void target;
    const allEditButtons = document.querySelectorAll('.task-item .task-actions .btn-secondary');
    let focusTarget = null;
    if (allEditButtons.length > 0) {
      // Prefer the edit button of the task that now sits at the same index.
      const idx = Math.min(before, allEditButtons.length - 1);
      focusTarget = allEditButtons[idx];
    }
    if (focusTarget) {
      focusTarget.focus();
    } else {
      const activeFilterButton = document.querySelector(
        '.filters button[aria-pressed="true"]'
      ) || document.querySelector('.filters button');
      if (activeFilterButton) {
        activeFilterButton.focus();
      }
    }
  });
  actions.appendChild(deleteButton);

  item.appendChild(main);

  if (task.description) {
    const description = document.createElement('p');
    description.className = 'task-description';
    description.textContent = task.description;
    item.appendChild(description);
  }

  item.appendChild(actions);

  list.appendChild(item);
}

function render() {
  const list = document.getElementById('task-list');
  const emptyState = document.getElementById('empty-state');
  clearChildren(list);

  const visible = filterTasks(tasks, activeFilter);
  for (const task of visible) {
    renderTaskItem(task, list, emptyState);
  }

  if (visible.length === 0) {
    emptyState.textContent = EMPTY_MESSAGES[activeFilter] || EMPTY_MESSAGES.all;
    emptyState.hidden = false;
  } else {
    emptyState.hidden = true;
  }

  // Update filter button pressed state.
  document.querySelectorAll('.filters button').forEach((button) => {
    const pressed = button.dataset.filter === activeFilter;
    button.setAttribute('aria-pressed', pressed ? 'true' : 'false');
  });
}

function init() {
  tasks = loadTasks(window.localStorage);
  activeFilter = 'all';
  editingId = null;
  editErrorShown = false;

  const form = document.getElementById('add-form');
  const titleInput = document.getElementById('title-input');
  const descriptionInput = document.getElementById('description-input');

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const trimmed = titleInput.value.trim();
    if (!trimmed) {
      // Refused silently - keep focus on the Title field.
      titleInput.focus();
      return;
    }
    const task = createTask(trimmed, descriptionInput.value);
    tasks = addTask(tasks, task);
    save();
    titleInput.value = '';
    descriptionInput.value = '';
    render();
    titleInput.focus();
  });

  document.querySelectorAll('.filters button').forEach((button) => {
    button.addEventListener('click', () => {
      activeFilter = button.dataset.filter || 'all';
      editingId = null;
      editErrorShown = false;
      render();
    });
  });

  render();
}

if (typeof document !== 'undefined') init();
