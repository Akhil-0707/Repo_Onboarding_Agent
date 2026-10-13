import { act, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";

import { commonPrefixLength, revealStep, useSmoothText } from "./useSmoothText";

describe("revealStep", () => {
  it("flows at least at the minimum speed and never overshoots", () => {
    expect(revealStep(0, 10, 50, false)).toBeCloseTo(2.25); // 45 chars/s floor
    expect(revealStep(9, 10, 100, false)).toBe(10);
    expect(revealStep(10, 10, 16, false)).toBe(10);
  });

  it("speeds up when it falls behind, more so once the answer is complete", () => {
    const streaming = revealStep(0, 600, 16, false);
    const finishing = revealStep(0, 600, 16, true);
    expect(streaming).toBeCloseTo(16); // 600 chars over ~0.6 s
    expect(finishing).toBeGreaterThan(streaming * 2);
  });

  it("ignores negative and very long frames", () => {
    expect(revealStep(5, 100, -40, false)).toBe(5);
    expect(revealStep(0, 10_000, 5_000, false)).toBeLessThan(1100); // capped at one 64 ms frame
  });
});

describe("commonPrefixLength", () => {
  it("counts the shared start", () => {
    expect(commonPrefixLength("They live in", "They lived")).toBe(9);
    expect(commonPrefixLength("", "abc")).toBe(0);
  });
});

describe("useSmoothText", () => {
  it("reveals text over several frames and reports when it has caught up", () => {
    let now = 0;
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => frames.push(cb));
    const runFrame = () =>
      act(() => {
        now += 16;
        frames.shift()?.(now);
      });

    const { result, rerender } = renderHook(({ text, done }) => useSmoothText(text, done), {
      initialProps: { text: "Hello there, reader", done: false },
    });
    expect(result.current.text).toBe("");
    for (let i = 0; i < 5; i++) runFrame(); // ~0.7 characters per 16 ms frame at first
    expect(result.current.text.length).toBeGreaterThan(0);
    expect(result.current.caughtUp).toBe(false);

    // A rewrite keeps only the shared start, then carries on to the new text.
    rerender({ text: "Hello world", done: true });
    for (let i = 0; i < 60 && frames.length; i++) runFrame();
    expect(result.current).toEqual({ text: "Hello world", caughtUp: true });
  });

  it("still runs after StrictMode's mount, unmount and remount", () => {
    let now = 0;
    let nextId = 1;
    const frames = new Map<number, FrameRequestCallback>(); // cancelled frames really go away
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      frames.set(nextId, cb);
      return nextId++;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => void frames.delete(id));
    const { result } = renderHook(() => useSmoothText("Streams in dev mode too", true), {
      wrapper: StrictMode,
    });
    for (let i = 0; i < 120 && frames.size; i++) {
      act(() => {
        now += 16;
        const [id, cb] = frames.entries().next().value!;
        frames.delete(id);
        cb(now);
      });
    }
    expect(result.current).toEqual({ text: "Streams in dev mode too", caughtUp: true });
  });

  it("shows everything at once with reduced motion", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) => ({ matches: query.includes("reduce") }) as MediaQueryList,
    );
    const { result } = renderHook(() => useSmoothText("All at once", false));
    expect(result.current).toEqual({ text: "All at once", caughtUp: true });
  });
});
