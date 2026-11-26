import { useState } from 'react';
import type { Task } from '../types';

interface TaskItemProps {
  task: Task;
  isEditing: boolean;
  editValue: string;
  onEditStart: () => void;
  onSaveEdit: (newTitle: string) => void;
  onCancelEdit: () => void;
  onEditInputChange: (value: string) => void;
  onToggle: () => void;
  onDelete: () => void;
}

export default function TaskItem({
  task,
  isEditing,
  editValue,
  onEditStart,
  onSaveEdit,
  onCancelEdit,
  onEditInputChange,
  onToggle,
  onDelete,
}: TaskItemProps) {
  const [isInvalid, setIsInvalid] = useState(false);

  const handleSave = () => {
    if (!editValue.trim()) {
      setIsInvalid(true);
      return;
    }
    setIsInvalid(false);
    onSaveEdit(editValue);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    } else if (e.key === 'Escape') {
      onCancelEdit();
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '12px 16px',
        marginBottom: '8px',
        backgroundColor: '#fff',
        borderRadius: '4px',
        border: '1px solid #E5E7EB',
        gap: '12px',
      }}
    >
      <input
        type="checkbox"
        checked={task.completed}
        onChange={onToggle}
        aria-label="Done"
        style={{
          width: '20px',
          height: '20px',
          cursor: 'pointer',
          accentColor: '#2563eb',
        }}
      />

      {isEditing ? (
        <div style={{ flex: 1, display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input
            type="text"
            value={editValue}
            onChange={(e) => {
              onEditInputChange(e.target.value);
              if (isInvalid && e.target.value.trim()) {
                setIsInvalid(false);
              }
            }}
            onKeyDown={handleKeyDown}
            aria-label="Edit title"
            style={{
              flex: 1,
              padding: '8px',
              border: isInvalid ? '2px solid #dc2626' : '1px solid #E5E7EB',
              borderRadius: '4px',
              fontSize: '16px',
              outline: 'none',
            }}
            onFocus={(e) => {
              if (!isInvalid) {
                e.target.style.borderColor = '#2563eb';
              }
            }}
            onBlur={(e) => {
              if (!isInvalid) {
                e.target.style.borderColor = '#E5E7EB';
              }
            }}
          />
          <button
            onClick={handleSave}
            aria-label="Save"
            style={{
              padding: '8px 16px',
              backgroundColor: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 500,
            }}
          >
            Save
          </button>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span
            style={{
              fontSize: '16px',
              color: '#111827',
              textDecoration: task.completed ? 'line-through' : 'none',
              opacity: task.completed ? 0.6 : 1,
              fontWeight: 500,
            }}
          >
            {task.title}
          </span>
          {task.description && (
            <span
              style={{
                fontSize: '14px',
                color: '#6B7280',
                opacity: task.completed ? 0.6 : 1,
              }}
            >
              {task.description}
            </span>
          )}
        </div>
      )}

      {!isEditing && (
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={onEditStart}
            aria-label="Edit"
            style={{
              padding: '6px 12px',
              backgroundColor: 'transparent',
              color: '#2563eb',
              border: '1px solid #2563eb',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            aria-label="Delete"
            style={{
              padding: '6px 12px',
              backgroundColor: '#dc2626',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
