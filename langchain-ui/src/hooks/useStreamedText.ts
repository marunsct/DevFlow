import { useEffect, useRef, useState } from 'react';

/**
 * Reveal a block of text the way a chat model appears to write it.
 *
 * The backend cannot stream tokens to the dashboard. `AgentActivityStream`
 * publishes one event per finished assistant message (`on_llm_end`), because the
 * alternative - a Redis publish and an SSE frame per token - multiplies event
 * volume by three orders of magnitude for a panel that is narration, not a
 * record. So a paragraph the model spent twenty seconds producing lands in the
 * feed in a single frame, and a reader watching a long run sees nothing, then a
 * wall, then nothing again.
 *
 * Revealing it on the client closes that gap at no cost to the run: the pacing
 * is cosmetic, the content is already complete and correct, and nothing here can
 * fail in a way that loses a message - the full text is returned as soon as the
 * reveal ends, and immediately if it never starts.
 */

/** Milliseconds of reveal per character. */
const MS_PER_CHARACTER = 7;

/** Floor and ceiling on a reveal, whatever the length. */
const MIN_DURATION_MS = 260;

/**
 * A long message must not hold the feed hostage.
 *
 * Messages reach 2,000 characters (the publisher's clip limit). At a constant
 * per-character rate that would take fourteen seconds, during which later
 * updates queue up behind it and the panel is less live, not more. Capped, a
 * long message simply reveals faster - which is also what a real token stream
 * looks like, since throughput does not fall as a response gets longer.
 */
const MAX_DURATION_MS = 1400;

const prefersReducedMotion = (): boolean => {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
};

export interface StreamedText {
  /** The portion to render right now. */
  visible: string;
  /** True while more is still being revealed. */
  streaming: boolean;
}

/**
 * @param text     the complete message.
 * @param enabled  whether to animate; false renders it whole and immediately.
 * @param onTick   called after each frame, so a pinned scroller can follow the
 *                 growing text. Kept as a callback rather than a state update
 *                 so a feed of several hundred rows is not re-rendered 60 times
 *                 a second to animate one of them.
 * @param onDone   called once the text is fully revealed, so the caller can
 *                 record that this message has had its turn and must not be
 *                 replayed when the next poll returns a new array.
 */
export function useStreamedText(
  text: string,
  enabled: boolean,
  onTick?: () => void,
  onDone?: () => void,
): StreamedText {
  // Read once per mount. It is a media query, not reactive state, and a reader
  // who changes the setting mid-reveal is not a case worth a listener.
  const [reduceMotion] = useState(prefersReducedMotion);
  const animate = enabled && text.length > 0 && !reduceMotion;

  // Progress is stored *with* the text it belongs to, so a new message derives
  // its own starting point during render instead of being reset by an effect.
  // Resetting in an effect meant one painted frame of the previous message's
  // length applied to the new one.
  const [progress, setProgress] = useState(() => ({ text, count: animate ? 0 : text.length }));
  const count = progress.text === text ? progress.count : animate ? 0 : text.length;

  // Held in refs so a caller may pass inline callbacks without restarting the
  // reveal on every render, and assigned in an effect rather than during render:
  // a render-phase ref write is re-run by StrictMode's double invocation, and
  // this hook has no business behaving differently in development.
  const tickRef = useRef(onTick);
  const doneRef = useRef(onDone);
  useEffect(() => {
    tickRef.current = onTick;
    doneRef.current = onDone;
  });

  useEffect(() => {
    if (!animate) return;

    const duration = Math.min(
      MAX_DURATION_MS,
      Math.max(MIN_DURATION_MS, text.length * MS_PER_CHARACTER),
    );
    const started = performance.now();

    let frame = requestAnimationFrame(function step(now: number) {
      const elapsed = Math.min(1, (now - started) / duration);
      setProgress({ text, count: Math.ceil(elapsed * text.length) });
      tickRef.current?.();
      if (elapsed < 1) frame = requestAnimationFrame(step);
      else doneRef.current?.();
    });

    return () => cancelAnimationFrame(frame);
  }, [text, animate]);

  const streaming = animate && count < text.length;
  return { visible: streaming ? text.slice(0, count) : text, streaming };
}
