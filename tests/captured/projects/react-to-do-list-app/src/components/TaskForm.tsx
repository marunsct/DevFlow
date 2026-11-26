import React from 'react';

interface TaskFormProps {
  title: string;
  description: string;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAdd: () => void;
}

export default function TaskForm({
  title,
  description,
  onTitleChange,
  onDescriptionChange,
  onAdd,
}: TaskFormProps) {
  const [isTouched, setIsTouched] = React.useState(false);
  const [hasError, setHasError] = React.useState(false);

  const handleAddClick = () => {
    setIsTouched(true);
    if (!title.trim()) {
      setHasError(true);
      return;
    }
    setHasError(false);
    onAdd();
  };

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    onTitleChange(value);
    if (hasError) {
      setHasError(false);
    }
  };

  return (
    <div style={{ marginBottom: '16px' }}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        <div>
          <label htmlFor="title" style={{ display: 'block', marginBottom: '4px', fontSize: '16px' }}>
            Title
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={handleTitleChange}
            aria-label="Title"
            style={{
              width: '100%',
              padding: '8px',
              fontSize: '16px',
              border: hasError ? '2px solid #dc2626' : '1px solid #E5E7EB',
              outline: 'none',
              boxSizing: 'border-box',
            }}
            onFocus={(e) => {
              if (!hasError) e.target.style.borderColor = '#2563eb';
            }}
            onBlur={(e) => {
              if (!hasError) e.target.style.borderColor = '#E5E7EB';
            }}
          />
        </div>
        <div>
          <label htmlFor="description" style={{ display: 'block', marginBottom: '4px', fontSize: '16px' }}>
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            aria-label="Description"
            rows={3}
            style={{
              width: '100%',
              padding: '8px',
              fontSize: '14px',
              border: '1px solid #E5E7EB',
              outline: 'none',
              boxSizing: 'border-box',
              resize: 'vertical',
            }}
            onFocus={(e) => (e.target.style.borderColor = '#2563eb')}
            onBlur={(e) => (e.target.style.borderColor = '#E5E7EB')}
          />
        </div>
        <button
          onClick={handleAddClick}
          aria-label="Add task"
          style={{
            padding: '8px 16px',
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '16px',
            alignSelf: 'flex-start',
          }}
        >
          Add task
        </button>
      </div>
    </div>
  );
}
