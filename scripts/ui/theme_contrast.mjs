// Contrast of every declared pair, in every theme and accent (plan Part 15.2).
//   node scripts/ui/theme_contrast.mjs
// Reads langchain-ui/src/index.css, resolves each theme's tokens, and fails when a
// foreground/background pair is under 4.5:1 (7:1 for the contrast theme, 3:1 for
// borders and the focus ring against their surface). Exit status 1 on any failure.
import fs from 'fs';

const css = fs.readFileSync(new URL('../../langchain-ui/src/index.css', import.meta.url), 'utf8');

function block(selector) {
  const at = css.indexOf(selector + ' {');
  if (at < 0) return null;
  const body = css.slice(at + selector.length + 2, css.indexOf('}', at));
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}
// graphite is the base; each other theme and accent overrides some tokens.
const base = block(':root,\n[data-theme="graphite"],\n:root[data-theme="system"]') ?? {};
const themes = {
  graphite: { ...base },
  paper: { ...base, ...block('[data-theme="paper"]') },
  contrast: { ...base, ...block('[data-theme="contrast"]') },
};
const accents = ['violet', 'teal', 'amber', 'rose', 'neutral'];
for (const accent of accents) {
  themes[`graphite+${accent}`] = { ...themes.graphite, ...block(`:root[data-accent="${accent}"]`) };
  themes[`paper+${accent}`] = {
    ...themes.paper, ...block(`:root[data-accent="${accent}"]`),
    ...block(`:root[data-theme="paper"][data-accent="${accent}"]`),
    ...block(':root[data-theme="paper"][data-accent]'),
  };
}

const hex = (value) => {
  const m = /^#([0-9a-f]{6})$/i.exec(value ?? '');
  return m ? [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) : null;
};
const rgba = (value) => {
  const m = /^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/.exec(value ?? '');
  return m ? { rgb: [+m[1], +m[2], +m[3]], a: +m[4] } : null;
};
const lum = ([r, g, b]) => {
  const f = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const colour = (value, over) => {
  const solid = hex(value);
  if (solid) return solid;
  const a = rgba(value);
  if (!a || !over) return null;
  return a.rgb.map((c, i) => Math.round(c * a.a + over[i] * (1 - a.a)));   // composited on its surface
};
const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

const failures = [];
let checked = 0;
for (const [name, t] of Object.entries(themes)) {
  const need = name === 'contrast' ? 7 : 4.5;
  const pair = (label, fg, bg, min = need) => {
    const surface = hex(t[bg]) ?? hex(t['--bg-surface']);
    const f = colour(t[fg], surface), b = colour(t[bg], hex(t['--bg-surface']));
    if (!f || !b) { failures.push(`${name}: ${label} - ${fg} or ${bg} is not a colour`); return; }
    checked += 1;
    const r = ratio(f, b);
    if (r < min) failures.push(`${name}: ${label} ${r.toFixed(2)}:1 < ${min}:1  (${fg} ${t[fg]} on ${bg} ${t[bg]})`);
  };
  for (const bg of ['--bg-canvas', '--bg-surface', '--bg-raised', '--bg-inset', '--bg-overlay', '--bg-overlay-strong']) {
    pair(`text on ${bg}`, '--fg', bg);
    pair(`muted text on ${bg}`, '--fg-muted', bg);
    pair(`subtle text on ${bg}`, '--fg-subtle', bg);
    if (bg.includes('overlay')) continue;   // only body text sits on an overlay
    pair(`accent text on ${bg}`, '--accent-text', bg);
    for (const s of ['ok', 'warn', 'danger', 'info']) pair(`${s} text on ${bg}`, `--status-${s}-fg`, bg);
  }
  pair('text on an accent fill', '--fg-on-accent', '--accent');
  pair('text on a hovered accent fill', '--fg-on-accent', '--accent-hover');
  for (const s of ['ok', 'warn', 'danger', 'info']) pair(`${s} text on its fill`, `--status-${s}-fg`, `--status-${s}-bg`);
  pair('attention text on its fill', '--status-attention-fg', '--status-attention-bg');
  pair('code text', '--code-fg', '--code-bg');
  pair('added line', '--diff-add-fg', '--diff-add-bg');
  pair('removed line', '--diff-del-fg', '--diff-del-bg');
  // Non-text: the focus ring and a control's border against the surface.
  pair('focus ring on the surface', '--ring', '--bg-surface', 3);
  pair('strong border on the surface', '--border-strong', '--bg-surface', 3);
}
console.log(`${checked} pairs checked across ${Object.keys(themes).length} theme/accent sets`);
if (failures.length) { console.log(failures.join('\n')); process.exit(1); }
console.log('every pair holds');
