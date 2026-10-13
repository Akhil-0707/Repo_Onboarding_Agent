import { act, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { revealUnits, unitGap, useLineReveal } from "./useLineReveal";

describe("revealUnits", () => {
  it("hides the line still being written until the answer is done", () => {
    expect(revealUnits("First line\nSecond li", false)).toEqual(["First line\n"]);
    expect(revealUnits("First line\nSecond li", true)).toEqual(["First line\n", "Second li"]);
    expect(revealUnits("No newline yet", false)).toEqual([]);
    expect(revealUnits("", true)).toEqual([]);
  });

  it("splits a long one-line paragraph into whole sentences", () => {
    expect(revealUnits("It parses argv. Then it dispatches! Does it wor", false)).toEqual([
      "It parses argv. ",
      "Then it dispatches! ",
    ]);
  });

  it("does not split list markers, inline code or code blocks", () => {
    expect(revealUnits("1. Options come first. Then", false)).toEqual(["1. Options come first. "]);
    expect(revealUnits("Call `a. b` now. x", false)).toEqual(["Call `a. b` now. "]);
    expect(revealUnits("```\nfoo. bar. baz\n```\nDone. ", false)).toEqual([
      "```\n",
      "foo. bar. baz\n",
      "```\n",
      "Done. ",
    ]);
  });

  it("always joins back into the original text", () => {
    const text = "A. B\n\n1. C. D\n- `e.f` g. h";
    expect(revealUnits(text, true).join("")).toBe(text);
  });
});

describe("unitGap", () => {
  it("shortens the pause when many units are waiting", () => {
    expect(unitGap(1)).toBeGreaterThan(unitGap(10));
  });
});

describe("useLineReveal", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // Small steps, so React renders (and arms the next line's timer) between them, as in real time.
  const advance = (ms: number) => {
    for (let elapsed = 0; elapsed <= ms; elapsed += 20) {
      act(() => {
        vi.advanceTimersByTime(Math.min(20, ms - elapsed));
      });
    }
  };

  it("shows one complete unit at a time, then the rest once the answer is done", () => {
    const { result, rerender } = renderHook(({ text, done }) => useLineReveal(text, done), {
      initialProps: { text: "One\nTwo\nThree\nFour is still be", done: false },
    });
    advance(0);
    expect(result.current.text).toBe("One\n"); // the first line shows at once
    advance(160);
    expect(result.current.text).toBe("One\nTwo\n");
    advance(1000);
    expect(result.current).toEqual({ text: "One\nTwo\nThree\n", caughtUp: false });

    rerender({ text: "One\nTwo\nThree\nFour is still being written.", done: true });
    advance(1000);
    expect(result.current).toEqual({
      text: "One\nTwo\nThree\nFour is still being written.",
      caughtUp: true,
    });
  });

  it("swaps in the final text line for line instead of starting over", () => {
    const { result, rerender } = renderHook(({ text, done }) => useLineReveal(text, done), {
      initialProps: { text: "See `a.js`.\nMore.\n", done: false },
    });
    advance(500);
    expect(result.current.text).toBe("See `a.js`.\nMore.\n");
    rerender({ text: "See [a.js].\nMore.\n", done: true });
    expect(result.current).toEqual({ text: "See [a.js].\nMore.\n", caughtUp: true });
  });

  it("keeps a steady pace while lines keep arriving", () => {
    const { result, rerender } = renderHook(({ text }) => useLineReveal(text, false), {
      initialProps: { text: "L1\n" },
    });
    advance(0);
    let text = "L1\n";
    for (let i = 2; i <= 6; i++) {
      text += `L${i}\n`;
      rerender({ text }); // a new line every 100 ms must not keep postponing the next one
      advance(100);
    }
    expect(result.current.text.split("\n").filter(Boolean).length).toBeGreaterThanOrEqual(3);
  });

  it("still runs under StrictMode", () => {
    const { result } = renderHook(() => useLineReveal("A\nB\nC", true), { wrapper: StrictMode });
    advance(2000);
    expect(result.current).toEqual({ text: "A\nB\nC", caughtUp: true });
  });

  it("shows all complete lines at once with reduced motion", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) => ({ matches: query.includes("reduce") }) as MediaQueryList,
    );
    const { result } = renderHook(() => useLineReveal("A\nB\nhalf", false));
    expect(result.current).toEqual({ text: "A\nB\n", caughtUp: false });
  });
});
