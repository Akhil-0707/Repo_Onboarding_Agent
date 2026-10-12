import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDots,
  dotCount,
  drawDots,
  drawTrail,
  pruneTrail,
  startDotField,
  stepDots,
} from "./dotField";
import type { Dot, TrailPoint } from "./dotField";

const dot = (x: number, y: number, vx = 0, vy = 0): Dot => ({ x, y, vx, vy, r: 1 });

function fakeContext() {
  return {
    clearRect: vi.fn(),
    setTransform: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    quadraticCurveTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    lineWidth: 0,
    strokeStyle: "",
    fillStyle: "",
  };
}

function canvasWith(ctx: ReturnType<typeof fakeContext>) {
  const canvas = document.createElement("canvas");
  canvas.getContext = (() => ctx) as unknown as typeof canvas.getContext;
  return canvas;
}

function mockReducedMotion(reduce: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) => ({ matches: reduce && query.includes("reduce") }) as MediaQueryList,
  );
}

describe("dot field", () => {
  afterEach(() => {
    document.documentElement.className = "";
  });

  it("scales the number of dots with the screen, within limits", () => {
    expect(dotCount(320, 200)).toBe(24);
    expect(dotCount(1280, 800)).toBe(64);
    expect(dotCount(4000, 3000)).toBe(90);
    expect(createDots(1280, 800)).toHaveLength(64);
  });

  it("drifts slowly and wraps around the edges", () => {
    const dots = [dot(10, 10, 10, 0), dot(-25, 50), dot(100, 830)];
    stepDots(dots, 0.5, 1000, 800, null);
    expect(dots[0]).toMatchObject({ x: 15, y: 10 });
    expect(dots[1]!.x).toBe(-25 + 1040);
    expect(dots[2]!.y).toBe(830 - 840);
  });

  it("pushes dots away from the cursor, only nearby", () => {
    const near = dot(110, 100);
    const far = dot(400, 100);
    stepDots([near, far], 0.1, 1000, 800, { x: 100, y: 100 });
    expect(near.x).toBeGreaterThan(110);
    expect(near.y).toBe(100);
    expect(far.x).toBe(400);
  });

  it("links close dots only", () => {
    const ctx = fakeContext();
    const palette = { rgb: "1 2 3", alpha: 0.2, lineAlpha: 0.1, trailAlpha: 0.5 };
    drawDots(
      ctx as unknown as CanvasRenderingContext2D,
      [dot(0, 0), dot(60, 0), dot(500, 0)],
      600,
      400,
      palette,
    );
    expect(ctx.stroke).toHaveBeenCalledTimes(1);
    expect(ctx.strokeStyle).toBe("rgb(1 2 3 / 0.050)");
    expect(ctx.fill).toHaveBeenCalledTimes(3);
    expect(ctx.fillStyle).toBe("rgb(1 2 3 / 0.2)");
  });

  it("forgets trace points once they have faded, and caps their number", () => {
    const trail: TrailPoint[] = [
      { x: 0, y: 0, t: 0 },
      { x: 5, y: 0, t: 500 },
      { x: 9, y: 0, t: 900 },
    ];
    pruneTrail(trail, 1000);
    expect(trail.map((p) => p.t)).toEqual([500, 900]);

    const long = Array.from({ length: 200 }, (_, i) => ({ x: i, y: 0, t: 1000 }));
    pruneTrail(long, 1000);
    expect(long).toHaveLength(96);
    expect(long[0]!.x).toBe(104);
  });

  it("draws the trace fading and thinning towards its tail", () => {
    const ctx = fakeContext();
    const palette = { rgb: "1 2 3", alpha: 0.2, lineAlpha: 0.1, trailAlpha: 0.5 };
    const widths: number[] = [];
    ctx.stroke.mockImplementation(() => widths.push(ctx.lineWidth));
    const trail: TrailPoint[] = [
      { x: 0, y: 0, t: 400 },
      { x: 10, y: 0, t: 700 },
      { x: 20, y: 5, t: 1000 },
    ];

    drawTrail(ctx as unknown as CanvasRenderingContext2D, trail, 1000, palette);
    expect(ctx.quadraticCurveTo).toHaveBeenCalledTimes(2);
    expect(widths[0]).toBeLessThan(widths[1]!); // older segment is thinner
    expect(ctx.strokeStyle).toBe("rgb(1 2 3 / 0.500)"); // newest point at full strength
    expect(ctx.lineTo).toHaveBeenLastCalledWith(20, 5); // reaches the cursor

    ctx.stroke.mockClear();
    drawTrail(ctx as unknown as CanvasRenderingContext2D, trail.slice(0, 1), 1000, palette);
    expect(ctx.stroke).not.toHaveBeenCalled();
  });

  it("animates every frame and stops when torn down", () => {
    mockReducedMotion(false);
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => frames.push(cb));
    const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const ctx = fakeContext();

    const stop = startDotField(canvasWith(ctx));
    expect(ctx.setTransform).toHaveBeenCalled();
    frames.shift()!(16);
    frames.shift()!(32);
    expect(ctx.clearRect).toHaveBeenCalledTimes(3); // initial draw + two frames
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 5, clientY: 5 }));
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 40, clientY: 5 }));
    frames.shift()!(48);
    expect(ctx.quadraticCurveTo).toHaveBeenCalled(); // the cursor trace

    stop();
    expect(cancel).toHaveBeenCalled();
  });

  it("draws once and stays still under reduced motion", () => {
    mockReducedMotion(true);
    const raf = vi.spyOn(window, "requestAnimationFrame");
    const ctx = fakeContext();

    const stop = startDotField(canvasWith(ctx));
    expect(ctx.clearRect).toHaveBeenCalledTimes(1);
    expect(raf).not.toHaveBeenCalled();
    stop();
  });

  it("does nothing without a 2D context", () => {
    const stop = startDotField(document.createElement("canvas"));
    expect(stop()).toBeUndefined();
  });
});
