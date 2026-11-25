/**
 * A bar between two panels that resizes the one it belongs to (plan UX.5): dragged with a pointer, or moved with the
 * arrow keys once it has focus. `from` says which edge the panel grows from, so dragging always follows the pointer.
 */
import React, { useRef } from 'react';
import { cx } from '../../ui';

export const Splitter: React.FC<{
  label: string;
  /** `x`: a vertical bar resizing a width; `y`: a horizontal bar resizing a height. */
  axis: 'x' | 'y';
  /** The panel sits before the bar (left, above) or after it (right, below). */
  from: 'before' | 'after';
  size: number;
  min: number;
  max: number;
  onSize: (size: number) => void;
  /** The pointer let go or a key moved it: the size to remember. */
  onSettle?: (size: number) => void;
}> = ({ label, axis, from, size, min, max, onSize, onSettle }) => {
  const drag = useRef<{ at: number; size: number } | null>(null);
  const clamp = (value: number) => Math.round(Math.min(max, Math.max(min, value)));
  const sign = from === 'before' ? 1 : -1;

  const onKeyDown = (event: React.KeyboardEvent) => {
    const step = event.shiftKey ? 64 : 16;
    const keys: Record<string, number> = axis === 'x'
      ? { ArrowRight: step * sign, ArrowLeft: -step * sign }
      : { ArrowDown: step * sign, ArrowUp: -step * sign };
    if (event.key in keys) {
      event.preventDefault();
      const next = clamp(size + keys[event.key]);
      onSize(next);
      onSettle?.(next);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      const next = event.key === 'Home' ? min : max;
      onSize(next);
      onSettle?.(next);
    }
  };

  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'}
      aria-valuenow={size}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        drag.current = { at: axis === 'x' ? event.clientX : event.clientY, size };
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const moved = (axis === 'x' ? event.clientX : event.clientY) - drag.current.at;
        onSize(clamp(drag.current.size + moved * sign));
      }}
      onPointerUp={() => {
        if (!drag.current) return;
        drag.current = null;
        onSettle?.(size);
      }}
      className={cx(
        'group relative z-10 shrink-0 touch-none select-none bg-border',
        'focus-visible:outline-none focus-visible:bg-[var(--ring)]',
        axis === 'x' ? 'w-px cursor-col-resize' : 'h-px cursor-row-resize',
      )}
    >
      {/* A wider grip than the line it draws. */}
      <span aria-hidden="true" className={cx(
        'absolute transition-colors group-hover:bg-accent/40',
        axis === 'x' ? 'inset-y-0 -left-1 -right-1' : 'inset-x-0 -top-1 -bottom-1',
      )} />
    </div>
  );
};
