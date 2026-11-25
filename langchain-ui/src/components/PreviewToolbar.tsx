/**
 * The preview's one toolbar row (plan UX.3): reload, a path field that opens a page under the signed link, and the
 * frame's size as a device (fill, phone, tablet, a custom size), turned on its side on asking. The panel's own
 * controls (start and stop, Page or Requests, pointing, the status) sit at its two ends.
 */
import React, { useState } from 'react';
import { Monitor, RotateCw, RefreshCw, Ruler, Smartphone, Tablet } from 'lucide-react';
import { DEVICE_SIZES, type DeviceSize } from '../lib/previewPath';
import { cx } from '../ui';

export interface FrameSize { device: DeviceSize['id']; width: number; height: number; turned: boolean }

const ICONS: Record<DeviceSize['id'], React.ReactNode> = {
  fill: <Monitor size={14} />,
  phone: <Smartphone size={14} />,
  tablet: <Tablet size={14} />,
  custom: <Ruler size={14} />,
};

/** The frame's width and height in pixels, or null to fill the panel. */
export function frameBox(size: FrameSize): { width: number; height: number } | null {
  if (size.device === 'fill') return null;
  return size.turned ? { width: size.height, height: size.width } : { width: size.width, height: size.height };
}

const tool = 'inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-text-secondary transition-colors hover:bg-overlay hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] disabled:opacity-40';

export const ToolbarDivider: React.FC = () => <span aria-hidden="true" className="mx-1 h-5 w-px shrink-0 bg-border" />;

export const PreviewToolbar: React.FC<{
  start?: React.ReactNode;
  end?: React.ReactNode;
  /** Reload, the path and the sizes: only while a page is shown. */
  framed: boolean;
  path: string;
  onGo: (path: string) => void;
  onReload: () => void;
  size: FrameSize;
  onSize: (size: FrameSize) => void;
}> = ({ start, end, framed, path, onGo, onReload, size, onSize }) => {
  const [draft, setDraft] = useState(path);
  const [shownPath, setShownPath] = useState(path);
  // The field follows the page it opened: a path refused leaves the last good one in place to be corrected.
  if (shownPath !== path) {
    setShownPath(path);
    setDraft(path);
  }
  const box = frameBox(size);
  const choose = (device: DeviceSize) =>
    onSize({ ...size, device: device.id, width: device.id === 'custom' ? size.width || device.width : device.width, height: device.id === 'custom' ? size.height || device.height : device.height });

  return (
    <div role="toolbar" aria-label="Preview" className="flex min-h-10 flex-wrap items-center gap-1 border-b border-border bg-surface px-2 py-1">
      {start}
      {framed && (
        <>
          <ToolbarDivider />
          <button type="button" className={tool} onClick={onReload} aria-label="Reload the page" title="Reload the page">
            <RefreshCw size={14} aria-hidden="true" />
          </button>
          <form
            className="flex min-w-40 flex-1 items-center rounded-md border border-border bg-inset focus-within:ring-2 focus-within:ring-[var(--ring)]"
            onSubmit={(event) => { event.preventDefault(); onGo(draft); }}
          >
            <span className="select-none border-r border-border px-2 font-mono text-[11px] text-text-muted" title="Every path opens under this preview's own signed link">preview</span>
            <input
              aria-label="Path in the product"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="/"
              className="h-7 min-w-0 flex-1 bg-transparent px-2 font-mono text-[12px] text-text-primary outline-none placeholder:text-text-muted/60"
            />
          </form>
          <ToolbarDivider />
          <div role="group" aria-label="Device size" className="flex items-center">
            {DEVICE_SIZES.map((device) => {
              const on = size.device === device.id;
              const name = device.id === 'fill' || device.id === 'custom' ? device.label : `${device.label} (${device.width} × ${device.height})`;
              return (
                <button key={device.id} type="button" aria-pressed={on} aria-label={name} title={name} onClick={() => choose(device)}
                  className={cx(tool, on && 'bg-overlay-strong text-text-primary')}>
                  <span aria-hidden="true">{ICONS[device.id]}</span>
                </button>
              );
            })}
            {size.device === 'custom' && (
              <span className="ml-1 flex items-center gap-1 font-mono text-[12px] text-text-secondary">
                <input type="number" min={200} max={3840} aria-label="Width in pixels" value={size.width}
                  onChange={(event) => onSize({ ...size, width: Math.max(0, Number(event.target.value) || 0) })}
                  className="h-7 w-16 rounded-md border border-border bg-inset px-1.5 text-text-primary tabular-nums" />
                <span aria-hidden="true">×</span>
                <input type="number" min={200} max={3840} aria-label="Height in pixels" value={size.height}
                  onChange={(event) => onSize({ ...size, height: Math.max(0, Number(event.target.value) || 0) })}
                  className="h-7 w-16 rounded-md border border-border bg-inset px-1.5 text-text-primary tabular-nums" />
              </span>
            )}
            <button type="button" className={tool} disabled={size.device === 'fill'} aria-label="Turn the device" title="Turn the device"
              onClick={() => onSize({ ...size, turned: !size.turned })}>
              <RotateCw size={14} aria-hidden="true" />
            </button>
            {box && <span className="ml-1 font-mono text-[11px] tabular-nums text-text-muted">{box.width}×{box.height}</span>}
          </div>
        </>
      )}
      {end}
    </div>
  );
};
