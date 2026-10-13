import { describe, expect, it } from "vitest";

import { makeStep } from "../test/fixtures";
import { formatElapsed, tourProgress } from "./tourProgress";

const analyze = (overrides: Parameters<typeof makeStep>[0] = {}) =>
  makeStep({ key: "analyze", label: "AI analysis", status: "running", ...overrides });

describe("tourProgress", () => {
  it("shows the file being read while researching", () => {
    const view = tourProgress(
      analyze({
        phase: "research",
        logs: [
          { ts: "", level: "info", message: "Model is back online; resuming the analysis." },
          { ts: "", level: "info", message: "Guided Tour: Reading 'lib/command.js'" },
        ],
      }),
      20,
    );
    expect(view.stage).toBe(0);
    expect(view.activity).toBe("Reading 'lib/command.js'");
  });

  it("keeps moving with time but never past the current stage", () => {
    const early = tourProgress(analyze({ phase: "research" }), 10);
    const later = tourProgress(analyze({ phase: "research" }), 400);
    expect(later.fraction).toBeGreaterThan(early.fraction);
    expect(later.fraction).toBeLessThanOrEqual(0.55); // still researching: stays below writing

    const writing = tourProgress(analyze({ phase: "writing", progress: 60 }), 30);
    expect(writing.stage).toBe(1);
    expect(writing.fraction).toBeCloseTo(0.6); // real progress wins over a low estimate
    expect(tourProgress(analyze({ phase: "writing" }), 9999).fraction).toBeLessThanOrEqual(0.88);
  });

  it("reports checking, waiting and done", () => {
    expect(tourProgress(analyze({ phase: "checking" }), 0).stage).toBe(2);
    expect(tourProgress(analyze({ status: "waiting" }), 0).waiting).toBe(true);
    expect(tourProgress(analyze({ status: "done", progress: 100 }), 0)).toMatchObject({
      stage: 3,
      fraction: 1,
    });
    expect(tourProgress(undefined, 0)).toMatchObject({ stage: 0, waiting: false });
  });
});

describe("formatElapsed", () => {
  it("shows minutes and seconds", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(84.9)).toBe("1:24");
  });
});
