import { useState, useEffect } from 'react';
import type { Task, FilterType } from './types';
import { readTasks, saveTasks } from './storage';
import TaskForm from './components/TaskForm';
import FilterButtons from './components/FilterButtons';
import TaskList from './components/TaskList';

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<FilterType>('all');
  const [title, setTitle] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');

  useEffect(() => {
    try {
      const initialTasks = readTasks();
      setTasks(initialTasks);
    } catch (e) {
      // Ignore storage errors on mount if localStorage is unavailable
    }
  }, []);

  useEffect(() => {
    try {
      saveTasks(tasks);
    } catch (e) {
      // Ignore storage errors if localStorage is unavailable
    }
  }, [tasks]);

  const handleAddTask = () => {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      return;
    }
    const newTask: Task = {
      id: Date.now().toString(),
      title: trimmedTitle,
      description: description,
      completed: false,
    };
    setTasks((prev) => [...prev, newTask]);
    setTitle('');
    setDescription('');
  };

  const handleToggle = (id: string) => {
    setTasks((prev) =>
      prev.map((task) =>
        task.id === id ? { ...task, completed: !task.completed } : task
      )
    );
  };

  const handleDelete = (id: string) => {
    setTasks((prev) => prev.filter((task) => task.id !== id));
    if (editingId === id) {
      setEditingId(null);
    }
  };

  const handleEditStart = (id: string, currentTitle: string) => {
    setEditingId(id);
    setEditValue(currentTitle);
  };

  const handleSaveEdit = (newTitle: string) => {
    if (!newTitle.trim()) {
      return;
    }
    setTasks((prev) =>
      prev.map((task) =>
        task.id === editingId ? { ...task, title: newTitle.trim() } : task
      )
    );
    setEditingId(null);
    setEditValue('');
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditValue('');
  };

  const handleFilterChange = (newFilter: FilterType) => {
    setFilter(newFilter);
  };

  const handleEditInputChange = (value: string) => {
    setEditValue(value);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '16px' }}>
      <h1>Simple To-Do List App</h1>
      <TaskForm
        title={title}
        description={description}
        onTitleChange={setTitle}
        onDescriptionChange={setDescription}
        onAdd={handleAddTask}
      />
      <FilterButtons currentFilter={filter} onFilterChange={handleFilterChange} />
      <TaskList
        tasks={tasks}
        filter={filter}
        editingId={editingId}
        editValue={editValue}
        onToggle={handleToggle}
        onDelete={handleDelete}
        onEditStart={handleEditStart}
        onSaveEdit={handleSaveEdit}
        onCancelEdit={handleCancelEdit}
        onEditInputChange={handleEditInputChange}
      />
    </div>
  );
}
