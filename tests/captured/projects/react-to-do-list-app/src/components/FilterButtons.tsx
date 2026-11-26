import type { FilterType } from '../types';

interface FilterButtonsProps {
  currentFilter: FilterType;
  onFilterChange: (filter: FilterType) => void;
}

export default function FilterButtons({ currentFilter, onFilterChange }: FilterButtonsProps) {
  const filters: FilterType[] = ['all', 'active', 'completed'];
  const labels: Record<FilterType, string> = {
    all: 'All',
    active: 'Active',
    completed: 'Completed',
  };

  return (
    <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
      {filters.map((filter) => {
        const isActive = currentFilter === filter;
        return (
          <button
            key={filter}
            onClick={() => onFilterChange(filter)}
            aria-pressed={isActive}
            style={{
              padding: '8px 16px',
              cursor: 'pointer',
              backgroundColor: isActive ? '#2563eb' : 'transparent',
              color: isActive ? '#ffffff' : '#111827',
              border: isActive ? 'none' : '1px solid #E5E7EB',
              borderRadius: '4px',
              fontSize: '14px',
              fontWeight: isActive ? 'bold' : 'normal',
              transition: 'background-color 0.2s, color 0.2s',
            }}
            onFocus={(e) => {
              e.currentTarget.style.outline = '2px solid #2563eb';
              e.currentTarget.style.outlineOffset = '2px';
            }}
            onBlur={(e) => {
              e.currentTarget.style.outline = 'none';
            }}
          >
            {labels[filter]}
          </button>
        );
      })}
    </div>
  );
}
