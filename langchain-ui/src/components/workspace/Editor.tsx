/**
 * The workspace's file view (plan UX.6): Monaco as the reader and the side-by-side diff, loaded only when a file is
 * opened, from the app's own bundle. On a touch screen (Monaco does not support phones), while it loads, or if it
 * fails to load, the present highlighter shows the file, so the text is always there. While the person holds the
 * turn (plan UX.14) the file can be changed: in Monaco, or in a plain text area where Monaco does not run.
 */
import React, { Suspense, useMemo } from 'react';
import { Code } from '../WorkspacePanel';

export interface EditorViewProps {
  path: string;
  text: string;
  /** Show the change: the text at the last accepted sprint beside the text now. */
  diff?: { base: string; since: string } | null;
  /** A line to bring into view and select (a search hit). */
  line?: number;
  /** The person holds the turn (plan UX.14): the text can be changed, and each change is passed on. */
  editable?: boolean;
  onEdit?: (text: string) => void;
}

const MonacoView = React.lazy(() => import('./monaco'));

/** Whether this screen is a phone or tablet, where Monaco is not supported. */
function touchFirst(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches;
}

/** The highlighter: the file, or the two versions side by side when a change is asked for. */
export const PlainView: React.FC<EditorViewProps> = ({ path, text, diff, editable, onEdit }) => (
  editable && !diff ? (
    <textarea aria-label={`The text of ${path}`} value={text} spellCheck={false} onChange={(event) => onEdit?.(event.target.value)}
      className="h-full w-full resize-none bg-code p-3 font-mono text-[13px] leading-5 text-text-primary focus-visible:outline-none" />
  ) : diff ? (
    <div className="grid h-full min-h-0 grid-cols-2 divide-x divide-border">
      <div className="min-h-0 overflow-auto" aria-label={`${path} at ${diff.since}`} tabIndex={0}>
        <p className="sticky top-0 border-b border-border bg-surface px-3 py-1 text-xs text-text-muted">At {diff.since}</p>
        <Code text={diff.base} path={path} />
      </div>
      <div className="min-h-0 overflow-auto" tabIndex={0}>
        <p className="sticky top-0 border-b border-border bg-surface px-3 py-1 text-xs text-text-muted">Now</p>
        <Code text={text} path={path} />
      </div>
    </div>
  ) : (
    <div className="h-full min-h-0 overflow-auto bg-code" tabIndex={0}>
      <Code text={text} path={path} />
    </div>
  )
);

class FallBack extends React.Component<{ plain: React.ReactNode; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.plain : this.props.children;
  }
}

export const Editor: React.FC<EditorViewProps> = (props) => {
  const plainOnly = useMemo(() => touchFirst(), []);
  const plain = <PlainView {...props} />;
  if (plainOnly) return plain;
  return (
    <FallBack plain={plain}>
      <Suspense fallback={plain}>
        <MonacoView {...props} />
      </Suspense>
    </FallBack>
  );
};
