import { useEffect, useRef, useState } from "react";

/** Slowest reveal speed (characters per second), so a trickle of tokens still flows. */
const MIN_CPS = 45;
/** The backlog is caught up over about this long; quicker once the answer is complete. */
const CATCH_UP_S = 0.6;
const FINISH_S = 0.25;
const MAX_FRAME_MS = 64;

/** Characters shown after one frame: the reveal speeds up when it falls behind, so bursty
 * network chunks become an even flow without ever lagging far behind the model. */
export function revealStep(shown: number, total: number, dtMs: number, done: boolean): number {
  const backlog = total - shown;
  if (backlog <= 0) return total;
  const cps = Math.max(MIN_CPS, backlog / (done ? FINISH_S : CATCH_UP_S));
  return Math.min(total, shown + (cps * Math.min(Math.max(dtMs, 0), MAX_FRAME_MS)) / 1000);
}

export function commonPrefixLength(a: string, b: string): number {
  const limit = Math.min(a.length, b.length);
  let i = 0;
  while (i < limit && a.charCodeAt(i) === b.charCodeAt(i)) i++;
  return i;
}

function animated(): boolean {
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  return !reduce && typeof window.requestAnimationFrame === "function";
}

/** Reveals `target` smoothly as it grows. If the target is rewritten (a retracted draft, the
 * final text replacing the preview), the reveal continues from the part both share. */
export function useSmoothText(target: string, done: boolean): { text: string; caughtUp: boolean } {
  const smooth = animated();
  const [shown, setShown] = useState("");
  const latest = useRef({ target, done });
  const visible = useRef("");
  const position = useRef(0);
  const frame = useRef(0);

  useEffect(() => {
    latest.current = { target, done };
    if (!smooth || frame.current) return; // a running loop reads the latest target each frame
    // One clock for both ends (some environments stamp frames on a different clock).
    let last = performance.now();
    const step = () => {
      const now = performance.now();
      const goal = latest.current.target;
      // If the text on screen was rewritten, keep only the part the new text still shares.
      const keep = commonPrefixLength(visible.current, goal);
      if (keep < visible.current.length) position.current = keep;
      position.current = revealStep(position.current, goal.length, now - last, latest.current.done);
      last = now;
      visible.current = goal.slice(0, Math.floor(position.current));
      setShown(visible.current);
      frame.current = visible.current === goal ? 0 : window.requestAnimationFrame(step);
    };
    frame.current = window.requestAnimationFrame(step);
  }, [target, done, smooth]);

  useEffect(
    () => () => {
      if (frame.current) window.cancelAnimationFrame(frame.current);
      frame.current = 0; // StrictMode remounts: the next mount must start its own loop
    },
    [],
  );

  if (!smooth) return { text: target, caughtUp: true };
  return { text: shown, caughtUp: shown === target };
}
