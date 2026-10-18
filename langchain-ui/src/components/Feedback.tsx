import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

/**
 * Toasts and a confirmation dialog in place of the browser's alert() and
 * confirm(): those block the page, carry no styling or next step, and a
 * screen reader hears them out of context. Errors are announced (role=alert),
 * other notices politely (role=status); the dialog keeps focus inside it,
 * closes on Escape, and gives focus back to whatever had it.
 */

type Kind = 'error' | 'info';
interface Toast { id: number; message: string; kind: Kind }
interface ConfirmRequest { title: string; message?: string; confirmLabel?: string; danger?: boolean }

interface Feedback {
  notify: (message: string, kind?: Kind) => void;
  confirm: (request: ConfirmRequest) => Promise<boolean>;
}

const FeedbackContext = createContext<Feedback>({
  notify: () => undefined,
  confirm: async () => false,
});

export const useFeedback = (): Feedback => useContext(FeedbackContext);

export const FeedbackProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [asking, setAsking] = useState<(ConfirmRequest & { resolve: (yes: boolean) => void }) | null>(null);
  const nextId = useRef(1);

  const notify = useCallback((message: string, kind: Kind = 'error') => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, kind }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), kind === 'error' ? 9000 : 5000);
  }, []);

  const confirm = useCallback(
    (request: ConfirmRequest) => new Promise<boolean>((resolve) => setAsking({ ...request, resolve })),
    [],
  );

  const answer = (yes: boolean) => {
    asking?.resolve(yes);
    setAsking(null);
  };

  return (
    <FeedbackContext.Provider value={{ notify, confirm }}>
      {children}
      <div className="fixed top-20 right-4 z-[90] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.kind === 'error' ? 'alert' : 'status'}
            className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-xl ${
              toast.kind === 'error'
                ? 'border-danger/40 bg-[#2a1520] text-red-200'
                : 'border-primary/40 bg-[#171c3a] text-indigo-100'
            }`}
          >
            <span className="flex-1 break-words">{toast.message}</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setToasts((current) => current.filter((t) => t.id !== toast.id))}
              className="rounded p-0.5 text-current/80 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      {asking && <ConfirmDialog request={asking} onAnswer={answer} />}
    </FeedbackContext.Provider>
  );
};

const ConfirmDialog: React.FC<{ request: ConfirmRequest; onAnswer: (yes: boolean) => void }> = ({ request, onAnswer }) => {
  const dialog = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    // A destructive choice starts on Cancel, so Enter never destroys by accident.
    (request.danger ? cancelRef.current : confirmRef.current)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onAnswer(false);
      } else if (e.key === 'Tab') {
        const order = [cancelRef.current, confirmRef.current].filter(Boolean) as HTMLElement[];
        const at = order.indexOf(document.activeElement as HTMLElement);
        e.preventDefault();
        order[(at + (e.shiftKey ? order.length - 1 : 1)) % order.length]?.focus();
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
  }, [request, onAnswer]);

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/60 p-4 overscroll-contain" onClick={() => onAnswer(false)}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={request.message ? 'confirm-message' : undefined}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl border border-border bg-[#111827] p-6 shadow-2xl"
      >
        <h2 id="confirm-title" className="text-base font-semibold text-white">{request.title}</h2>
        {request.message && (
          <p id="confirm-message" className="mt-2 text-sm text-text-secondary whitespace-pre-line">{request.message}</p>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={() => onAnswer(false)}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-white/5 hover:text-white"
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={() => onAnswer(true)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold text-white ${
              request.danger ? 'bg-red-700 hover:bg-red-600' : 'bg-primary hover:bg-primary-hover'
            }`}
          >
            {request.confirmLabel || 'Continue'}
          </button>
        </div>
      </div>
    </div>
  );
};
