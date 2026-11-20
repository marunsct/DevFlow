/**
 * A small read-only highlighter for the workspace view (plan WS.1): comments, strings, numbers and keywords,
 * chosen by the file's extension. Lexical only - no parsing, no editing - so one table covers every language a
 * run may build, and an unknown file is shown plain rather than wrongly.
 */

export type TokenKind = 'comment' | 'string' | 'number' | 'keyword' | 'plain';
export interface Token { kind: TokenKind; text: string }

interface Syntax {
  line: string[];
  block: [string, string][];
  quotes: string;
  /** Quotes that may run over a line end. */
  multiline: string;
  triple: boolean;
  keywords: Set<string>;
}

const words = (text: string) => new Set(text.split(/\s+/).filter(Boolean));

const C_LIKE = 'if else for while do switch case default break continue return new try catch finally throw class '
  + 'interface enum extends implements import package public private protected static final const void true false null this super';
const KEYWORDS: Record<string, Set<string>> = {
  js: words(`${C_LIKE} function let var async await yield export from as of in typeof instanceof delete undefined type readonly declare namespace keyof`),
  python: words('def class return if elif else for while in not and or is import from as with try except finally raise pass lambda yield async await None True False global nonlocal assert del break continue match case self'),
  go: words('package import func return if else for range switch case default break continue go defer select chan map struct interface type var const nil true false fallthrough goto'),
  rust: words('fn let mut pub use mod struct enum impl trait for in if else match loop while return break continue as ref move self Self crate super where async await dyn const static unsafe true false Some None Ok Err'),
  c: words(`${C_LIKE} int long short char float double bool boolean byte string var using namespace struct typedef sizeof unsigned signed auto virtual override async await fun val object when is in`),
  php: words(`${C_LIKE} function echo fn use namespace require require_once include array foreach as match readonly`),
  ruby: words('def end class module if elsif else unless case when while until for in do return yield begin rescue ensure raise then self nil true false and or not require attr_accessor'),
  shell: words('if then else elif fi for while do done case esac in function return export local set echo exit'),
  sql: words('select from where insert into values update set delete create table index primary key foreign references not null and or join left right inner on group by order limit as default unique drop alter'),
  none: new Set(),
};

const syntax = (s: Partial<Syntax> & { keywords: Set<string> }): Syntax =>
  ({ line: [], block: [], quotes: '\'"', multiline: '', triple: false, ...s });

const SLASHES = { line: ['//'], block: [['/*', '*/']] as [string, string][] };
const HASH = { line: ['#'] };
const BY_EXTENSION: Record<string, Syntax> = {};
const add = (extensions: string, value: Syntax) => { for (const ext of extensions.split(' ')) BY_EXTENSION[ext] = value; };
add('js jsx ts tsx mjs cjs mts cts', syntax({ ...SLASHES, quotes: '\'"`', multiline: '`', keywords: KEYWORDS.js }));
add('py pyi', syntax({ ...HASH, triple: true, keywords: KEYWORDS.python }));
add('go', syntax({ ...SLASHES, quotes: '"`', multiline: '`', keywords: KEYWORDS.go }));
add('rs', syntax({ ...SLASHES, quotes: '"', keywords: KEYWORDS.rust }));
add('java kt kts cs c h cc cpp hpp swift scala dart groovy gradle', syntax({ ...SLASHES, keywords: KEYWORDS.c }));
add('php', syntax({ line: ['//', '#'], block: SLASHES.block, keywords: KEYWORDS.php }));
add('rb rake gemspec', syntax({ ...HASH, keywords: KEYWORDS.ruby }));
add('sh bash zsh', syntax({ ...HASH, keywords: KEYWORDS.shell }));
add('yml yaml toml cfg conf properties dockerfile makefile', syntax({ ...HASH, keywords: KEYWORDS.none }));
add('ini', syntax({ line: ['#', ';'], keywords: KEYWORDS.none }));
add('sql', syntax({ line: ['--'], block: SLASHES.block, keywords: KEYWORDS.sql }));
add('css scss less', syntax({ block: SLASHES.block, line: [], keywords: KEYWORDS.none }));
add('json jsonc', syntax({ quotes: '"', keywords: words('true false null') }));
add('html htm xml svg vue svelte', syntax({ block: [['<!--', '-->']], quotes: '"', keywords: KEYWORDS.none }));

/** The syntax for a path, by its extension or, for `Dockerfile` and `Makefile`, its name; none when unknown. */
function syntaxOf(path: string): Syntax | null {
  const name = (path.split('/').pop() || '').toLowerCase();
  const ext = name.includes('.') ? name.split('.').pop()! : name;
  return BY_EXTENSION[ext] ?? null;
}

const WORD = /[A-Za-z_$][\w$]*/y;
const NUMBER = /\d[\w.]*/y;

/** The text as tokens, each line its own list: a token running over a line end is split at it. */
export function highlight(text: string, path: string): Token[][] {
  const lines: Token[][] = [[]];
  const push = (kind: TokenKind, value: string) => {
    value.split('\n').forEach((part, index) => {
      if (index > 0) lines.push([]);
      if (!part) return;
      const line = lines[lines.length - 1];
      const previous = line[line.length - 1];
      if (previous && previous.kind === kind) previous.text += part;
      else line.push({ kind, text: part });
    });
  };
  const s = syntaxOf(path);
  if (!s) {
    push('plain', text);
    return lines;
  }
  let i = 0;
  const until = (end: string, from: number) => {
    const at = text.indexOf(end, from);
    return at === -1 ? text.length : at + end.length;
  };
  while (i < text.length) {
    const block = s.block.find(([open]) => text.startsWith(open, i));
    if (block) {
      const end = until(block[1], i + block[0].length);
      push('comment', text.slice(i, end));
      i = end;
      continue;
    }
    if (s.line.some((mark) => text.startsWith(mark, i))) {
      const end = text.indexOf('\n', i);
      const stop = end === -1 ? text.length : end;
      push('comment', text.slice(i, stop));
      i = stop;
      continue;
    }
    const ch = text[i];
    const triple = s.triple && ['"""', "'''"].find((mark) => text.startsWith(mark, i));
    if (triple) {
      const end = until(triple, i + 3);
      push('string', text.slice(i, end));
      i = end;
      continue;
    }
    if (s.quotes.includes(ch)) {
      let j = i + 1;
      while (j < text.length && text[j] !== ch && (text[j] !== '\n' || s.multiline.includes(ch))) j += text[j] === '\\' ? 2 : 1;
      const end = Math.min(text.length, j + (text[j] === ch ? 1 : 0));
      push('string', text.slice(i, end));
      i = end;
      continue;
    }
    WORD.lastIndex = i;
    const word = WORD.exec(text);
    if (word) {
      push(s.keywords.has(word[0]) ? 'keyword' : 'plain', word[0]);
      i += word[0].length;
      continue;
    }
    NUMBER.lastIndex = i;
    const number = NUMBER.exec(text);
    if (number) {
      push('number', number[0]);
      i += number[0].length;
      continue;
    }
    push('plain', ch);
    i += 1;
  }
  return lines;
}
