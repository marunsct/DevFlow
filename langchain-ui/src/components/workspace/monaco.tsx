/**
 * The workspace's reader and side-by-side diff on Monaco (plan UX.6), loaded only when the workspace opens a file.
 *
 * Bundled with the app, never fetched from a CDN: the editor core, the contributions a reader uses (find, folding,
 * bracket matching, word highlight, go to line, sticky scroll, the diff editor) and every language's colouring, each
 * language its own small chunk loaded when a file of it opens. No language service or its worker: only the editor's
 * own worker, which the diff needs. Everything is read-only.
 */
import { useEffect, useRef } from 'react';
import * as monaco from 'monaco-editor/editor/editor.api';
import 'monaco-editor/editor/browser/coreCommands';
import 'monaco-editor/editor/browser/widget/codeEditor/codeEditorWidget';
import 'monaco-editor/editor/browser/widget/diffEditor/diffEditor.contribution';
import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching';
import 'monaco-editor/editor/contrib/clipboard/browser/clipboard';
import 'monaco-editor/editor/contrib/contextmenu/browser/contextmenu';
import 'monaco-editor/editor/contrib/find/browser/findController';
import 'monaco-editor/features/find/register';
import 'monaco-editor/editor/contrib/folding/browser/folding';
import 'monaco-editor/editor/contrib/multicursor/browser/multicursor';
import 'monaco-editor/editor/contrib/readOnlyMessage/browser/contribution';
import 'monaco-editor/editor/contrib/smartSelect/browser/smartSelect';
import 'monaco-editor/editor/contrib/stickyScroll/browser/stickyScrollContribution';
import 'monaco-editor/editor/contrib/tokenization/browser/tokenization';
import 'monaco-editor/editor/contrib/unicodeHighlighter/browser/unicodeHighlighter';
import 'monaco-editor/editor/contrib/wordHighlighter/browser/wordHighlighter';
import 'monaco-editor/editor/contrib/wordOperations/browser/wordOperations';
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneGotoLineQuickAccess';
import 'monaco-editor/editor/common/standaloneStrings';
// The icon font's styles: the package's exports map names scripts only, so these two are reached by path.
import '../../../node_modules/monaco-editor/esm/vs/base/browser/ui/codicons/codicon/codicon.css';
import '../../../node_modules/monaco-editor/esm/vs/base/browser/ui/codicons/codicon/codicon-modifiers.css';
import 'monaco-editor/languages/definitions/register.all';
import EditorWorker from 'monaco-editor/editor/editor.worker?worker';
import type { EditorViewProps } from './Editor';

(self as unknown as { MonacoEnvironment: monaco.Environment }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

/** A CSS colour as Monaco takes it: `#rrggbb` or `#rrggbbaa`. */
function hex(color: string, fallback: string): string {
  const value = color.trim();
  if (/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(value)) return value;
  if (/^#[0-9a-f]{3}$/i.test(value)) return `#${[...value.slice(1)].map((c) => c + c).join('')}`;
  const parts = value.match(/^rgba?\(([^)]+)\)$/i)?.[1].split(/[\s,/]+/).filter(Boolean);
  if (!parts || parts.length < 3) return fallback;
  const byte = (n: number) => Math.round(Math.min(255, Math.max(0, n))).toString(16).padStart(2, '0');
  const alpha = parts[3] === undefined ? '' : byte(parseFloat(parts[3]) * (parts[3].endsWith('%') ? 2.55 : 255));
  return `#${byte(+parts[0])}${byte(+parts[1])}${byte(+parts[2])}${alpha}`;
}

/** The app's own theme, read from its tokens, so the editor follows graphite, paper or high contrast. */
function applyTheme(): void {
  const style = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => hex(style.getPropertyValue(name), fallback);
  const light = style.getPropertyValue('color-scheme').includes('light');
  monaco.editor.defineTheme('devflow', {
    base: light ? 'vs' : 'vs-dark',
    inherit: true,
    rules: [],
    colors: {
      'editor.background': token('--code-bg', light ? '#ffffff' : '#12141a'),
      'editor.foreground': token('--code-fg', light ? '#1b1f27' : '#d6dbe5'),
      'editorLineNumber.foreground': token('--fg-subtle', '#9aa3b2'),
      'editorLineNumber.activeForeground': token('--fg', '#e8eaef'),
      'editor.lineHighlightBackground': token('--bg-overlay', '#ffffff0d'),
      'editor.selectionBackground': token('--accent-soft', '#6e8bff24'),
      'editorWidget.background': token('--bg-raised', '#242830'),
      'editorWidget.border': token('--border', '#343945'),
      'editorGutter.background': token('--code-bg', '#12141a'),
      'diffEditor.insertedLineBackground': token('--diff-add-bg', '#3fb68b24'),
      'diffEditor.removedLineBackground': token('--diff-del-bg', '#e5605c24'),
      'focusBorder': token('--ring', '#8fa6ff'),
      'scrollbarSlider.background': token('--scrollbar', '#343945'),
    },
  });
  monaco.editor.setTheme('devflow');
}

const OPTIONS: monaco.editor.IEditorOptions = {
  readOnly: true,
  domReadOnly: true,
  automaticLayout: true,
  scrollBeyondLastLine: false,
  fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
  fontSize: 13,
  lineHeight: 20,
  renderLineHighlight: 'line',
  smoothScrolling: true,
  stickyScroll: { enabled: true },
  minimap: { enabled: true, renderCharacters: false },
  readOnlyMessage: { value: 'Read-only: the run writes these files.' },
};

let models = 0;
/** A model of a file's text: Monaco picks its language from the file's name and extension, plain text when none. */
function modelOf(text: string, path: string): monaco.editor.ITextModel {
  models += 1;
  return monaco.editor.createModel(text, undefined, monaco.Uri.from({ scheme: 'workspace', path: `/${models}/${path}` }));
}

/** One theme for every editor on the page, redrawn when the app's theme changes. */
function useTheme(): void {
  useEffect(() => {
    applyTheme();
    const watch = new MutationObserver(applyTheme);
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class', 'style'] });
    return () => watch.disconnect();
  }, []);
}

// Where each file was scrolled to, so a tab opened again comes back where it was.
const viewStates = new Map<string, monaco.editor.ICodeEditorViewState | null>();

export default function MonacoView({ path, text, diff, line }: EditorViewProps) {
  const host = useRef<HTMLDivElement>(null);
  const reader = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const differ = useRef<monaco.editor.IStandaloneDiffEditor | null>(null);
  const shownPath = useRef<string | null>(null);
  const diffing = !!diff;
  const base = diff?.base ?? '';
  useTheme();

  // The reader: one editor, one model per file shown.
  useEffect(() => {
    if (diffing || !host.current) return undefined;
    const editor = monaco.editor.create(host.current, { ...OPTIONS, theme: 'devflow' });
    reader.current = editor;
    return () => {
      if (shownPath.current) viewStates.set(shownPath.current, editor.saveViewState());
      shownPath.current = null;
      editor.getModel()?.dispose();
      editor.dispose();
      reader.current = null;
    };
  }, [diffing]);

  useEffect(() => {
    const editor = reader.current;
    if (!editor || diffing) return;
    const sameFile = shownPath.current === path;
    if (shownPath.current && !sameFile) viewStates.set(shownPath.current, editor.saveViewState());
    const kept = sameFile ? editor.saveViewState() : viewStates.get(path);
    const before = editor.getModel();
    editor.setModel(modelOf(text, path));
    before?.dispose();
    shownPath.current = path;
    if (kept) editor.restoreViewState(kept);
  }, [path, text, diffing]);

  useEffect(() => {
    const editor = reader.current;
    if (!editor || !line || diffing) return;
    editor.revealLineInCenter(line);
    editor.setSelection(new monaco.Range(line, 1, line, editor.getModel()?.getLineMaxColumn(line) ?? 1));
  }, [line, path, diffing]);

  // The side-by-side diff: the text at the last accepted sprint on the left, the text now on the right.
  useEffect(() => {
    if (!diffing || !host.current) return undefined;
    const editor = monaco.editor.createDiffEditor(host.current, {
      ...OPTIONS,
      theme: 'devflow',
      originalEditable: false,
      renderSideBySide: true,
      useInlineViewWhenSpaceIsLimited: true,
      renderOverviewRuler: true,
      minimap: { enabled: false },
    });
    differ.current = editor;
    return () => {
      const models = editor.getModel();
      editor.dispose();
      models?.original.dispose();
      models?.modified.dispose();
      differ.current = null;
    };
  }, [diffing]);

  useEffect(() => {
    const editor = differ.current;
    if (!editor || !diffing) return;
    const before = editor.getModel();
    editor.setModel({ original: modelOf(base, path), modified: modelOf(text, path) });
    before?.original.dispose();
    before?.modified.dispose();
  }, [diffing, base, text, path]);

  return <div ref={host} className="h-full w-full" aria-label={diff ? `The change to ${path}` : `The text of ${path}`} role="region" />;
}
