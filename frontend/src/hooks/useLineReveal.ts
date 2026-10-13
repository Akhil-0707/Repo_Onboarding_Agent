import { useEffect, useRef, useState } from "react";

/** Pause between units, so a burst of text still reads as one line at a time. */
const LINE_GAP_MS = 160;
/** Shorter pause once several units are waiting, so the reveal never lags far behind. */
const FAST_GAP_MS = 60;
const FAST_AFTER_UNITS = 4;

/** Splits text into complete units: whole lines, and inside a line whole sentences (a model
 * often writes a long paragraph as one line). While streaming, the unit still being written
 * stays hidden. Joining the units gives back the original text. */
export function revealUnits(text: string, done: boolean): string[] {
  const units: string[] = [];
  let start = 0;
  let inFence = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "\n") {
      const unit = text.slice(start, i + 1);
      if (unit.trimStart().startsWith("```")) inFence = !inFence;
      units.push(unit);
      start = i + 1;
    } else if (!inFence && (ch === "." || ch === "!" || ch === "?") && text[i + 1] === " ") {
      const unit = text.slice(start, i + 2);
      const listMarker = /^\s*\d+[.)] $/.test(unit);
      const inCode = (unit.match(/`/g)?.length ?? 0) % 2 === 1;
      if (!listMarker && !inCode) {
        units.push(unit);
        start = i + 2;
        i++;
      }
    }
  }
  if (done && start < text.length) units.push(text.slice(start));
  return units;
}

export function unitGap(waiting: number): number {
  return waiting > FAST_AFTER_UNITS ? FAST_GAP_MS : LINE_GAP_MS;
}

function animated(): boolean {
  return !(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
}

/** Reveals `target` one complete line or sentence at a time. What is already shown stays put
 * when the final text replaces the draft (it is swapped in place, unit for unit). */
export function useLineReveal(target: string, done: boolean): { text: string; caughtUp: boolean } {
  const smooth = animated();
  const units = revealUnits(target, done);
  const [count, setCount] = useState(0);
  const total = useRef(units.length);
  const behind = count < units.length;

  useEffect(() => {
    total.current = units.length;
  });

  useEffect(() => {
    if (!smooth || !behind) return;
    // The first unit shows at once; later ones follow at a steady pace.
    const delay = count === 0 ? 0 : unitGap(total.current - count);
    const timer = window.setTimeout(() => setCount((c) => Math.min(c + 1, total.current)), delay);
    return () => window.clearTimeout(timer);
  }, [count, behind, smooth]);

  const shown = smooth ? Math.min(count, units.length) : units.length;
  return { text: units.slice(0, shown).join(""), caughtUp: done && shown >= units.length };
}
