/**
 * The count of runs waiting for the owner, on the browser tab: "(2) DevFlow.ai"
 * in the title and a dot with the number on the favicon, so a waiting gate is
 * seen from another tab. Pages set their own titles; the count is put back in
 * front of whatever they set.
 */
const PREFIX = /^\(\d+\+?\)\s/;

let shown = 0;
let watching = false;
let drawing = 0;
let plainIcon: string | null = null;

const label = (count: number): string => (count > 9 ? '9+' : String(count));

function putTheCountInTheTitle(): void {
  const bare = document.title.replace(PREFIX, '');
  const wanted = shown > 0 ? `(${label(shown)}) ${bare}` : bare;
  if (document.title !== wanted) document.title = wanted;
}

function watchTheTitle(): void {
  if (watching || typeof MutationObserver === 'undefined') return;
  const title = document.querySelector('title');
  if (!title) return;
  new MutationObserver(putTheCountInTheTitle).observe(title, { childList: true, characterData: true, subtree: true });
  watching = true;
}

function token(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function drawTheIcon(count: number): void {
  const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) return;
  plainIcon ??= link.href;
  const mine = ++drawing;
  if (count <= 0) {
    link.href = plainIcon;
    return;
  }
  const image = new Image();
  image.onload = () => {
    if (mine !== drawing) return;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.drawImage(image, 0, 0, 64, 64);
    context.fillStyle = token('--accent', '#6e8bff');
    context.beginPath();
    context.arc(44, 20, 20, 0, 2 * Math.PI);
    context.fill();
    context.fillStyle = token('--fg-on-accent', '#0b1020');
    context.font = 'bold 28px sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(label(count), 44, 21);
    link.href = canvas.toDataURL('image/png');
  };
  image.src = plainIcon;
}

export function showCountInTab(count: number): void {
  if (typeof document === 'undefined') return;
  const changed = count !== shown;
  shown = count;
  watchTheTitle();
  putTheCountInTheTitle();
  if (changed) drawTheIcon(count);
}
