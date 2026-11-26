import type { Task, FilterType } from '../types';
import TaskItem from './TaskItem';

interface TaskListProps {
  tasks: Task[];
  filter: FilterType;
  editingId: string | null;
  editValue: string;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onEditStart: (id: string, currentTitle: string) => void;
  onSaveEdit: (newTitle: string) => void;
  onCancelEdit: () => void;
  onEditInputChange: (value: string) => void;
}

export default function TaskList({
  tasks,
  filter,
  editingId,
  editValue,
  onToggle,
  onDelete,
  onEditStart,
  onSaveEdit,
  onCancelEdit,
  onEditInputChange,
}: TaskListProps) {
  const filteredTasks = tasks.filter((task) => {
    if (filter === 'active') return !task.completed;
    if (filter === 'completed') return task.completed;
    return true;
  });

  const isEmpty = filteredTasks.length === 0;
  const message =
    tasks.length === 0 ? 'No tasks yet' : 'No matching tasks';

  return (
    <div style={{ marginTop: '16px', flex: 1 }}>
      {isEmpty && (
        <div
          style={{
            textAlign: 'center',
            color: '#6B7280',
            padding: '32px 0',
          }}
        >
          {message}
        </div>
      )}
      <ul
        style={{
          listStyle: 'none',
          padding: 0,
          margin: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        {filteredTasks.map((task) => (
          <li key={task.id} style={{ marginBottom: '0' }}>
            <TaskItem
              task={task}
              isEditing={editingId === task.id}
              editValue={editValue}
              onEditStart={() => onEditStart(task.id, task.title)}
              onSaveEdit={onSaveEdit}
              onCancelEdit={onCancelEdit}
              onEditInputChange={onEditInputChange}
              onToggle={() => onToggle(task.id)}
              onDelete={() => onDelete(task.id)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
