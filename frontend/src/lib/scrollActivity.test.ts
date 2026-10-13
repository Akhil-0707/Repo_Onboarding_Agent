import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installScrollActivity, SCROLL_IDLE_MS } from "./scrollActivity";

describe("installScrollActivity", () => {
  let uninstall: () => void = () => undefined;
  beforeEach(() => {
    vi.useFakeTimers();
    uninstall = installScrollActivity();
  });
  afterEach(() => {
    uninstall();
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("marks a scroller while it scrolls and clears it once idle", () => {
    const box = document.createElement("div");
    document.body.append(box);
    box.dispatchEvent(new Event("scroll"));
    expect(box).toHaveAttribute("data-scrolling");

    vi.advanceTimersByTime(SCROLL_IDLE_MS - 100);
    box.dispatchEvent(new Event("scroll")); // still scrolling: stays visible
    vi.advanceTimersByTime(SCROLL_IDLE_MS - 100);
    expect(box).toHaveAttribute("data-scrolling");

    vi.advanceTimersByTime(200);
    expect(box).not.toHaveAttribute("data-scrolling");
  });

  it("marks the page itself when the document scrolls", () => {
    document.dispatchEvent(new Event("scroll"));
    expect(document.documentElement).toHaveAttribute("data-scrolling");
    uninstall();
    expect(document.documentElement).not.toHaveAttribute("data-scrolling");
    uninstall = () => undefined;
  });
});
