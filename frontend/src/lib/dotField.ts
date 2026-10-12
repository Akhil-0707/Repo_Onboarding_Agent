/** Live background: slowly drifting dots, faintly linked when close, nudged aside by the cursor,
 * plus a fading trace of the cursor's path (drawn on the canvas, so it stays behind content).
 *
 * Drawn on one fixed canvas (`components/LiveBackground.tsx`). Colours come from the
 * `--dots-*` variables in `index.css` and are re-read when the theme class changes. Under
 * `prefers-reduced-motion` the field is drawn once and stays still. */

export interface Dot {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
}

const AREA_PER_DOT = 16000;
const MIN_DOTS = 24;
const MAX_DOTS = 90;
const LINK_DISTANCE = 120;
const CURSOR_RADIUS = 140;
const CURSOR_PUSH = 60; // px/s at the cursor itself
const EDGE = 20; // dots wrap a little outside the viewport so they never pop in
const TRAIL_MS = 650; // how long a point of the cursor trace stays visible
const TRAIL_MAX_POINTS = 96;
const TRAIL_WIDTH = 2.5; // px at the cursor, tapering to nothing at the tail

export interface TrailPoint {
  x: number;
  y: number;
  t: number;
}

export function dotCount(width: number, height: number): number {
  return Math.max(MIN_DOTS, Math.min(MAX_DOTS, Math.round((width * height) / AREA_PER_DOT)));
}

export function createDots(width: number, height: number, random = Math.random): Dot[] {
  return Array.from({ length: dotCount(width, height) }, () => {
    const angle = random() * Math.PI * 2;
    const speed = 6 + random() * 10; // px/s: slow drift
    return {
      x: random() * width,
      y: random() * height,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      r: 1.2 + random() * 0.9,
    };
  });
}

/** Advances every dot by `dt` seconds: drift, cursor push, wrap around the edges. */
export function stepDots(
  dots: Dot[],
  dt: number,
  width: number,
  height: number,
  cursor: { x: number; y: number } | null,
): void {
  for (const dot of dots) {
    dot.x += dot.vx * dt;
    dot.y += dot.vy * dt;
    if (cursor) {
      const dx = dot.x - cursor.x;
      const dy = dot.y - cursor.y;
      const distance = Math.hypot(dx, dy);
      if (distance > 0 && distance < CURSOR_RADIUS) {
        const push = (1 - distance / CURSOR_RADIUS) ** 2 * CURSOR_PUSH * dt;
        dot.x += (dx / distance) * push;
        dot.y += (dy / distance) * push;
      }
    }
    if (dot.x < -EDGE) dot.x += width + 2 * EDGE;
    else if (dot.x > width + EDGE) dot.x -= width + 2 * EDGE;
    if (dot.y < -EDGE) dot.y += height + 2 * EDGE;
    else if (dot.y > height + EDGE) dot.y -= height + 2 * EDGE;
  }
}

interface Palette {
  rgb: string;
  alpha: number;
  lineAlpha: number;
  trailAlpha: number;
}

function readPalette(root: HTMLElement): Palette {
  const style = getComputedStyle(root);
  const number = (name: string, fallback: number) => {
    const value = Number.parseFloat(style.getPropertyValue(name));
    return Number.isFinite(value) ? value : fallback;
  };
  const rgb = style.getPropertyValue("--dots-rgb").trim() || "148 163 184";
  return {
    rgb,
    alpha: number("--dots-alpha", 0.3),
    lineAlpha: number("--dots-line-alpha", 0.12),
    trailAlpha: number("--trail-alpha", 0.45),
  };
}

export function drawDots(
  ctx: CanvasRenderingContext2D,
  dots: Dot[],
  width: number,
  height: number,
  palette: Palette,
): void {
  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 1;
  for (let i = 0; i < dots.length; i++) {
    const a = dots[i]!;
    for (let j = i + 1; j < dots.length; j++) {
      const b = dots[j]!;
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (distance >= LINK_DISTANCE) continue;
      const alpha = (1 - distance / LINK_DISTANCE) * palette.lineAlpha;
      ctx.strokeStyle = `rgb(${palette.rgb} / ${alpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }
  ctx.fillStyle = `rgb(${palette.rgb} / ${palette.alpha})`;
  for (const dot of dots) {
    ctx.beginPath();
    ctx.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** Drops trace points older than the trail's lifetime (and any beyond the cap). */
export function pruneTrail(trail: TrailPoint[], now: number): void {
  let stale = 0;
  while (stale < trail.length && now - trail[stale]!.t > TRAIL_MS) stale++;
  stale = Math.max(stale, trail.length - TRAIL_MAX_POINTS);
  if (stale > 0) trail.splice(0, stale);
}

/** The cursor trace: a smooth curve through the recent points (midpoint quadratics), fading and
 * thinning with age. */
export function drawTrail(
  ctx: CanvasRenderingContext2D,
  trail: TrailPoint[],
  now: number,
  palette: Palette,
): void {
  if (trail.length < 2) return;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  const mid = (a: TrailPoint, b: TrailPoint) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  for (let i = 1; i < trail.length; i++) {
    const prev = trail[i - 1]!;
    const point = trail[i]!;
    const life = 1 - Math.min(1, Math.max(0, now - point.t) / TRAIL_MS);
    if (life <= 0) continue;
    const start = i === 1 ? prev : mid(trail[i - 2]!, prev);
    const end = mid(prev, point);
    ctx.strokeStyle = `rgb(${palette.rgb} / ${(life * palette.trailAlpha).toFixed(3)})`;
    ctx.lineWidth = Math.max(0.5, life * TRAIL_WIDTH);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.quadraticCurveTo(prev.x, prev.y, end.x, end.y);
    ctx.stroke();
  }
  // Close the gap between the last midpoint and the cursor itself.
  const tail = trail[trail.length - 2]!;
  const head = trail[trail.length - 1]!;
  const end = mid(tail, head);
  ctx.beginPath();
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(head.x, head.y);
  ctx.stroke();
}

export function startDotField(canvas: HTMLCanvasElement): () => void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return () => undefined;
  const view = canvas.ownerDocument.defaultView ?? window;
  const root = canvas.ownerDocument.documentElement;
  const still = view.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

  let width = 0;
  let height = 0;
  let dots: Dot[] = [];
  let palette = readPalette(root);
  let cursor: { x: number; y: number } | null = null;
  const trail: TrailPoint[] = [];
  let frame = 0;
  let last: number | null = null;

  const resize = () => {
    width = view.innerWidth;
    height = view.innerHeight;
    const ratio = Math.min(2, view.devicePixelRatio || 1);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    // Keep the dots that still fit; top up or trim to the new density.
    dots = dots.filter((d) => d.x <= width + 20 && d.y <= height + 20);
    const wanted = dotCount(width, height);
    if (dots.length < wanted)
      dots.push(...createDots(width, height).slice(0, wanted - dots.length));
    dots.length = Math.min(dots.length, wanted);
    drawDots(ctx, dots, width, height, palette);
  };

  const tick = (now: number) => {
    const dt = last === null ? 0 : Math.min(0.05, (now - last) / 1000);
    last = now;
    stepDots(dots, dt, width, height, cursor);
    drawDots(ctx, dots, width, height, palette);
    pruneTrail(trail, now);
    drawTrail(ctx, trail, now, palette);
    frame = view.requestAnimationFrame(tick);
  };

  const onMove = (event: PointerEvent) => {
    if (event.pointerType === "touch") return;
    cursor = { x: event.clientX, y: event.clientY };
    // Coalesced events give every intermediate position, so fast strokes stay smooth.
    const t = view.performance.now();
    const points = event.getCoalescedEvents?.() ?? [];
    for (const p of points.length ? points : [event]) trail.push({ x: p.clientX, y: p.clientY, t });
  };
  const onLeave = () => {
    cursor = null;
  };
  const onVisibility = () => {
    last = null; // no jump after the tab was hidden
  };
  const themeObserver = new MutationObserver(() => {
    palette = readPalette(root);
    drawDots(ctx, dots, width, height, palette);
  });

  resize();
  view.addEventListener("resize", resize);
  themeObserver.observe(root, { attributes: true, attributeFilter: ["class"] });
  if (!still) {
    view.addEventListener("pointermove", onMove, { passive: true });
    root.addEventListener("pointerleave", onLeave);
    canvas.ownerDocument.addEventListener("visibilitychange", onVisibility);
    frame = view.requestAnimationFrame(tick);
  }

  return () => {
    view.cancelAnimationFrame(frame);
    view.removeEventListener("resize", resize);
    themeObserver.disconnect();
    view.removeEventListener("pointermove", onMove);
    root.removeEventListener("pointerleave", onLeave);
    canvas.ownerDocument.removeEventListener("visibilitychange", onVisibility);
  };
}
