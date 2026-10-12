import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installPointerEffects, tiltAngles } from "./pointerEffects";

const RECT = { left: 100, top: 50, width: 200, height: 100 };

function card(className: string): HTMLElement {
  const el = document.createElement("div");
  el.className = className;
  el.getBoundingClientRect = () => ({ ...RECT, right: 300, bottom: 150, x: 100, y: 50 }) as DOMRect;
  const child = document.createElement("span");
  el.append(child);
  document.body.append(el);
  return el;
}

function move(target: Element, clientX: number, clientY: number, pointerType = "mouse") {
  const event = new MouseEvent("pointermove", { bubbles: true, clientX, clientY });
  Object.defineProperty(event, "pointerType", { value: pointerType });
  target.dispatchEvent(event);
}

function mockReducedMotion(reduce: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) => ({ matches: reduce && query.includes("reduce") }) as MediaQueryList,
  );
}

describe("tiltAngles", () => {
  it("is flat at the centre", () => {
    expect(tiltAngles(RECT, 200, 100)).toEqual({ x: 0, y: 0 });
  });

  it("turns the card so the side under the pointer recedes", () => {
    // Top-right corner: right side back (positive Y), top back (positive X).
    expect(tiltAngles(RECT, 300, 50)).toEqual({ x: 4, y: 4 });
    expect(tiltAngles(RECT, 100, 150)).toEqual({ x: -4, y: -4 });
  });

  it("tilts wide cards less and clamps outside the card", () => {
    const wide = { left: 0, top: 0, width: 800, height: 100 };
    expect(tiltAngles(wide, 2000, 50)).toEqual({ x: 0, y: 1.25 });
  });

  it("ignores empty boxes", () => {
    expect(tiltAngles({ left: 0, top: 0, width: 0, height: 0 }, 5, 5)).toEqual({ x: 0, y: 0 });
  });
});

describe("installPointerEffects", () => {
  let uninstall: () => void = () => undefined;
  let queue: FrameRequestCallback[] = [];
  let now = 0;

  /** Runs animation frames (16 ms apart) until the effect goes idle. */
  function settle(maxFrames = 500) {
    for (let i = 0; i < maxFrames && queue.length; i++) {
      const callbacks = queue;
      queue = [];
      now += 16;
      callbacks.forEach((cb) => cb(now));
    }
  }

  beforeEach(() => {
    queue = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      queue.push(cb);
      return queue.length;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
  });

  afterEach(() => {
    uninstall();
    document.body.innerHTML = "";
  });

  it("moves the spotlight and eases the card under the pointer into its tilt", () => {
    mockReducedMotion(false);
    uninstall = installPointerEffects();
    const el = card("surface surface-hover");

    move(el.firstElementChild!, 300, 50);
    settle(1);
    expect(el.style.getPropertyValue("--spot-x")).toBe("200px");
    expect(el.style.getPropertyValue("--spot-y")).toBe("0px");
    // First frame: on its way, not there yet.
    const first = Number.parseFloat(el.style.getPropertyValue("--tilt-x"));
    expect(first).toBeGreaterThan(0);
    expect(first).toBeLessThan(4);
    expect(el.dataset.tilting).toBe("");

    settle();
    expect(queue).toHaveLength(0); // idle once arrived
    expect(el.style.getPropertyValue("--tilt-x")).toBe("4deg");
    expect(el.style.getPropertyValue("--tilt-y")).toBe("4deg");
    expect(el.style.getPropertyValue("--lift")).toBe("-3px");
  });

  it("settles the previous card back to flat when the pointer moves on", () => {
    mockReducedMotion(false);
    uninstall = installPointerEffects();
    const first = card("surface surface-hover");
    const second = card("surface surface-hover");

    move(first, 300, 50);
    settle();
    move(second, 300, 50);
    settle();

    expect(first.style.getPropertyValue("--tilt-x")).toBe("");
    expect(first.dataset.tilting).toBeUndefined();
    expect(second.style.getPropertyValue("--tilt-x")).toBe("4deg");

    window.dispatchEvent(new Event("scroll"));
    settle();
    expect(second.style.getPropertyValue("--tilt-x")).toBe("");
    expect(second.dataset.tilting).toBeUndefined();
  });

  it("only lights plain surfaces and skips tilt under reduced motion", () => {
    mockReducedMotion(true);
    uninstall = installPointerEffects();
    const panel = card("surface");
    const tile = card("surface surface-hover");

    move(panel, 150, 60);
    settle();
    move(tile, 300, 50);
    settle();

    expect(panel.style.getPropertyValue("--spot-x")).toBe("50px");
    expect(tile.style.getPropertyValue("--spot-x")).toBe("200px");
    expect(tile.style.getPropertyValue("--tilt-x")).toBe("");
  });

  it("ignores touch and cleans up once uninstalled", () => {
    mockReducedMotion(false);
    uninstall = installPointerEffects();
    const el = card("surface surface-hover");

    move(el, 300, 50, "touch");
    settle();
    expect(el.style.getPropertyValue("--spot-x")).toBe("");

    move(el, 300, 50);
    settle(3);
    uninstall();
    expect(el.style.getPropertyValue("--tilt-x")).toBe("");
    move(el, 100, 150);
    settle();
    expect(el.style.getPropertyValue("--spot-x")).toBe("200px");
  });
});
