import React, { useEffect, useId, useRef, useState } from 'react';
import { cx } from './cx';

export interface TabItem {
  id: string;
  label: React.ReactNode;
  content: React.ReactNode;
}

interface TabsProps {
  items: TabItem[];
  /** The query parameter that holds the selected tab, so a link or a reload opens the same one. */
  param?: string;
  initial?: string;
  label: string;
  className?: string;
}

function fromTheUrl(param?: string): string | null {
  if (!param || typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get(param);
}

/**
 * Tabs with one tab stop: arrow keys, Home and End move between tabs, Enter or
 * a click is not needed to show one (selection follows focus), and the choice is
 * kept in the address when `param` is given.
 */
export const Tabs: React.FC<TabsProps> = ({ items, param, initial, label, className }) => {
  const base = useId();
  const asked = fromTheUrl(param);
  const first = items.find((item) => item.id === asked)?.id ?? items.find((item) => item.id === initial)?.id ?? items[0]?.id;
  const [selected, setSelected] = useState(first);
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!param || !selected || typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    if (url.searchParams.get(param) === selected) return;
    url.searchParams.set(param, selected);
    window.history.replaceState(window.history.state, '', url);
  }, [param, selected]);

  const choose = (index: number) => {
    const item = items[(index + items.length) % items.length];
    if (!item) return;
    setSelected(item.id);
    tabs.current[(index + items.length) % items.length]?.focus();
  };

  const onKey = (event: React.KeyboardEvent, index: number) => {
    const moves: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: items.length - 1 };
    if (event.key in moves) {
      event.preventDefault();
      choose(moves[event.key]);
    }
  };

  return (
    <div className={className}>
      <div role="tablist" aria-label={label} className="flex gap-1 border-b border-border">
        {items.map((item, index) => {
          const on = item.id === selected;
          return (
            <button
              key={item.id}
              ref={(node) => { tabs.current[index] = node; }}
              type="button"
              role="tab"
              id={`${base}-tab-${item.id}`}
              aria-selected={on}
              aria-controls={`${base}-panel-${item.id}`}
              tabIndex={on ? 0 : -1}
              onClick={() => setSelected(item.id)}
              onKeyDown={(event) => onKey(event, index)}
              className={cx(
                '-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
                on ? 'border-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary',
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) => (
        <div
          key={item.id}
          role="tabpanel"
          id={`${base}-panel-${item.id}`}
          aria-labelledby={`${base}-tab-${item.id}`}
          hidden={item.id !== selected}
          tabIndex={0}
          className="pt-4 focus-visible:outline-none"
        >
          {item.id === selected && item.content}
        </div>
      ))}
    </div>
  );
};
