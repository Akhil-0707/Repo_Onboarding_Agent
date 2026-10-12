/** Cursor-driven effects: a spotlight on every `surface` and a 3D tilt on `surface-hover` cards.
 *
 * One delegated listener feeds a single animation-frame loop that writes CSS variables;
 * `index.css` draws the glow (`--spot-x/--spot-y`) and the tilt (`--tilt-x/--tilt-y/--lift`).
 * The tilt eases toward its target every frame (frame-rate independent) instead of restarting
 * a CSS transition on each pointer move, which keeps it smooth. Touch input is ignored and the
 * tilt is skipped under `prefers-reduced-motion`. */

const SPOT_SELECTOR = ".surface";
const TILT_SELECTOR = ".surface-hover";
const MAX_TILT_DEG = 4;
/** Wide cards tilt less so their far edge never swings more than a few pixels. */
const TILT_BUDGET_PX_DEG = 1000;
const LIFT_PX = -3;
/** Easing time constants (ms): quick to follow the cursor, a little slower to settle. */
const FOLLOW_MS = 90;
const SETTLE_MS = 180;
const MAX_FRAME_MS = 64;

export function tiltAngles(
  rect: Pick<DOMRect, "left" | "top" | "width" | "height">,
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  const clamp = (v: number) => Math.max(-1, Math.min(1, v));
  // -1..1 from the card's centre to its edges.
  const px = clamp(((clientX - rect.left) / rect.width) * 2 - 1);
  const py = clamp(((clientY - rect.top) / rect.height) * 2 - 1);
  const maxY = Math.min(MAX_TILT_DEG, TILT_BUDGET_PX_DEG / rect.width);
  const maxX = Math.min(MAX_TILT_DEG, TILT_BUDGET_PX_DEG / rect.height);
  // The card turns to face the cursor: the side under the pointer recedes.
  return { x: round(-py * maxX), y: round(px * maxY) };
}

function round(v: number): number {
  return Math.round(v * 100) / 100 || 0;
}

function closest(target: EventTarget | null, selector: string): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(selector) : null;
}

interface Tilt {
  x: number;
  y: number;
  lift: number;
  target: { x: number; y: number; lift: number };
}

export function installPointerEffects(doc: Document = document): () => void {
  const view = doc.defaultView ?? window;
  const reducedMotion = view.matchMedia?.("(prefers-reduced-motion: reduce)");
  const tilts = new Map<HTMLElement, Tilt>();
  let hovered: HTMLElement | null = null;
  let pending: PointerEvent | null = null;
  let frame = 0;
  let last: number | null = null;

  const schedule = () => {
    if (!frame) frame = view.requestAnimationFrame(tick);
  };

  const release = () => {
    if (hovered) tilts.get(hovered)!.target = { x: 0, y: 0, lift: 0 };
    hovered = null;
  };

  const handlePointer = (event: PointerEvent) => {
    const spot = closest(event.target, SPOT_SELECTOR);
    if (spot) {
      const rect = spot.getBoundingClientRect();
      spot.style.setProperty("--spot-x", `${Math.round(event.clientX - rect.left)}px`);
      spot.style.setProperty("--spot-y", `${Math.round(event.clientY - rect.top)}px`);
    }

    const card = reducedMotion?.matches ? null : closest(event.target, TILT_SELECTOR);
    if (card !== hovered) release();
    if (!card) return;
    hovered = card;
    const angles = tiltAngles(card.getBoundingClientRect(), event.clientX, event.clientY);
    const target = { ...angles, lift: LIFT_PX };
    const tilt = tilts.get(card);
    if (tilt) tilt.target = target;
    else {
      tilts.set(card, { x: 0, y: 0, lift: 0, target });
      card.dataset.tilting = "";
    }
  };

  const tick = (now: number) => {
    frame = 0;
    const dt = last === null ? 16 : Math.min(MAX_FRAME_MS, Math.max(0, now - last));
    last = now;
    if (pending) {
      handlePointer(pending);
      pending = null;
    }

    let moving = false;
    for (const [card, tilt] of tilts) {
      const following = card === hovered;
      const k = 1 - Math.exp(-dt / (following ? FOLLOW_MS : SETTLE_MS));
      const ease = (from: number, to: number) =>
        Math.abs(to - from) < 0.01 ? to : from + (to - from) * k;
      tilt.x = ease(tilt.x, tilt.target.x);
      tilt.y = ease(tilt.y, tilt.target.y);
      tilt.lift = ease(tilt.lift, tilt.target.lift);
      if (!following && tilt.x === 0 && tilt.y === 0 && tilt.lift === 0) {
        clear(card);
        tilts.delete(card);
        continue;
      }
      const { target } = tilt;
      if (tilt.x !== target.x || tilt.y !== target.y || tilt.lift !== target.lift) moving = true;
      card.style.setProperty("--tilt-x", `${round(tilt.x)}deg`);
      card.style.setProperty("--tilt-y", `${round(tilt.y)}deg`);
      card.style.setProperty("--lift", `${round(tilt.lift)}px`);
    }

    // Idle once every card has arrived; the next pointer move restarts the loop.
    if (moving) schedule();
    else last = null;
  };

  const onMove = (event: PointerEvent) => {
    if (event.pointerType === "touch") return;
    pending = event;
    schedule();
  };
  const onLeave = () => {
    pending = null;
    release();
    if (tilts.size) schedule();
  };

  doc.addEventListener("pointermove", onMove, { passive: true });
  doc.documentElement.addEventListener("pointerleave", onLeave);
  // Scrolling moves cards out from under a still pointer (capture: scroll does not bubble).
  view.addEventListener("scroll", onLeave, { passive: true, capture: true });
  return () => {
    if (frame) view.cancelAnimationFrame(frame);
    for (const card of tilts.keys()) clear(card);
    tilts.clear();
    doc.removeEventListener("pointermove", onMove);
    doc.documentElement.removeEventListener("pointerleave", onLeave);
    view.removeEventListener("scroll", onLeave, { capture: true });
  };
}

function clear(card: HTMLElement) {
  card.style.removeProperty("--tilt-x");
  card.style.removeProperty("--tilt-y");
  card.style.removeProperty("--lift");
  delete card.dataset.tilting;
}
