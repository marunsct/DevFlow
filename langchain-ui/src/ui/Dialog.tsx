import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { cx } from './cx';
import { focusables, trapTab } from './focus';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
  /** Where focus starts; the first focusable element when not given. */
  initialFocus?: React.RefObject<HTMLElement | null>;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  /** `side` is a drawer: full height at the right edge, for an artifact or a diff on a narrow screen. */
  placement?: 'center' | 'side';
}

const SIZES = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl' };

/**
 * A modal: focus moves in and stays in, Escape and the backdrop close it, the
 * page behind does not scroll, and focus goes back to what had it.
 */
export const Dialog: React.FC<DialogProps> = ({
  open, onClose, title, description, size = 'md', initialFocus, footer, children, placement = 'center',
}) => {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    (initialFocus?.current ?? focusables(panel.current)[0] ?? panel.current)?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      } else {
        trapTab(event, panel.current);
      }
    };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      before?.focus?.();
    };
  }, [open, onClose, initialFocus]);

  if (!open) return null;
  const side = placement === 'side';
  return createPortal(
    <div
      className={cx('fixed inset-0 z-[95] flex bg-scrim overscroll-contain', side ? 'justify-end' : 'items-center justify-center p-4')}
      onClick={onClose}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className={cx(
          'flex flex-col border border-border bg-surface-raised focus:outline-none',
          side ? 'h-full w-full max-w-xl' : cx('w-full rounded-2xl', SIZES[size]),
        )}
      >
        <div className="px-6 pt-6">
          <h2 id={titleId} className="text-base font-semibold text-text-primary">{title}</h2>
          {description && <p id={descriptionId} className="mt-2 text-sm text-text-secondary whitespace-pre-line">{description}</p>}
        </div>
        {children && <div className={cx('px-6 pt-4', side && 'flex-1 overflow-auto')}>{children}</div>}
        {footer && <div className="mt-6 flex justify-end gap-2 px-6 pb-6">{footer}</div>}
        {!footer && <div className="pb-6" />}
      </div>
    </div>,
    document.body,
  );
};

/** A side panel: the dialog at the right edge, full height. */
export const Drawer: React.FC<Omit<DialogProps, 'placement' | 'size'>> = (props) => <Dialog {...props} placement="side" />;
