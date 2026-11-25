/**
 * The workspace window's open files (plan UX.5), as an editor keeps them: one tab per file; a file opened with a
 * single choice goes into the one preview tab, which the next such file replaces; a file opened on purpose (a double
 * choice, or a preview tab chosen again) is kept. Closing the file shown shows its neighbour, the right one first.
 */

export interface EditorTab { path: string; kept: boolean }
export interface OpenFiles { tabs: EditorTab[]; active: string | null }

export const NONE_OPEN: OpenFiles = { tabs: [], active: null };

export function openFile(state: OpenFiles, path: string, keep = false): OpenFiles {
  const at = state.tabs.findIndex((tab) => tab.path === path);
  if (at >= 0) {
    const tabs = keep ? state.tabs.map((tab, index) => (index === at ? { ...tab, kept: true } : tab)) : state.tabs;
    return { tabs, active: path };
  }
  const tab = { path, kept: keep };
  const preview = state.tabs.findIndex((t) => !t.kept);
  if (preview >= 0) {
    return { tabs: state.tabs.map((t, index) => (index === preview ? tab : t)), active: path };
  }
  const after = state.tabs.findIndex((t) => t.path === state.active);
  const tabs = [...state.tabs];
  tabs.splice(after >= 0 ? after + 1 : tabs.length, 0, tab);
  return { tabs, active: path };
}

export function keepFile(state: OpenFiles, path: string): OpenFiles {
  return { ...state, tabs: state.tabs.map((tab) => (tab.path === path ? { ...tab, kept: true } : tab)) };
}

export function closeFile(state: OpenFiles, path: string): OpenFiles {
  const at = state.tabs.findIndex((tab) => tab.path === path);
  if (at < 0) return state;
  const tabs = state.tabs.filter((_, index) => index !== at);
  if (state.active !== path) return { tabs, active: state.active };
  return { tabs, active: (tabs[at] ?? tabs[at - 1])?.path ?? null };
}

/** Paths of the tree that hold every typed piece in order, the file's own name first, at most `most`. */
export function matchPaths(paths: string[], query: string, most = 50): string[] {
  const typed = query.trim().toLowerCase().replace(/\s+/g, '');
  if (!typed) return paths.slice(0, most);
  const inOrder = (text: string) => {
    let from = 0;
    for (const ch of typed) {
      from = text.indexOf(ch, from);
      if (from < 0) return false;
      from += 1;
    }
    return true;
  };
  const scored: { path: string; score: number }[] = [];
  for (const path of paths) {
    const lower = path.toLowerCase();
    if (!inOrder(lower)) continue;
    const name = lower.slice(lower.lastIndexOf('/') + 1);
    const score = name.startsWith(typed) ? 0 : name.includes(typed) ? 1 : lower.includes(typed) ? 2 : 3;
    scored.push({ path, score });
  }
  return scored.sort((a, b) => a.score - b.score || a.path.length - b.path.length).slice(0, most).map((s) => s.path);
}
