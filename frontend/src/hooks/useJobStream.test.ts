import { describe, expect, it } from "vitest";

import { makeJob } from "../test/fixtures";
import { jobReducer, parseStreamEvent } from "./useJobStream";
import type { JobStreamState } from "./useJobStream";

const initial: JobStreamState = { job: null, ended: false, connected: false, error: null };

describe("jobReducer", () => {
  it("applies snapshot, step, log and job events in order", () => {
    let state = jobReducer(initial, { type: "snapshot", job: makeJob() });
    expect(state.job?.steps[0]?.status).toBe("running");

    state = jobReducer(state, {
      type: "step",
      key: "clone",
      fields: { status: "done", message: "Shallow clone complete" },
      jobProgress: 40,
    });
    expect(state.job?.steps[0]).toMatchObject({
      status: "done",
      message: "Shallow clone complete",
    });
    expect(state.job?.progress).toBe(40);

    state = jobReducer(state, {
      type: "log",
      key: "parse",
      entry: { ts: "t", level: "info", message: "Parsed 3 files" },
    });
    expect(state.job?.steps[1]?.logs.map((l) => l.message)).toEqual(["Parsed 3 files"]);

    state = jobReducer(state, { type: "job", status: "done" });
    expect(state.job?.status).toBe("done");
    expect(state.job?.progress).toBe(100);

    state = jobReducer(state, { type: "end" });
    expect(state.ended).toBe(true);
  });

  it("marks terminal snapshots as ended", () => {
    const state = jobReducer(initial, { type: "snapshot", job: makeJob({ status: "failed" }) });
    expect(state.ended).toBe(true);
  });

  it("ignores incremental events before the first snapshot", () => {
    expect(jobReducer(initial, { type: "job", status: "done" })).toBe(initial);
  });
});

describe("parseStreamEvent", () => {
  it("parses step events and separates job progress", () => {
    const event = parseStreamEvent(
      "step",
      JSON.stringify({ type: "step", key: "parse", status: "running", job_progress: 55 }),
    );
    expect(event).toEqual({
      type: "step",
      key: "parse",
      fields: { status: "running" },
      jobProgress: 55,
    });
  });

  it("returns null for malformed or unknown events", () => {
    expect(parseStreamEvent("step", "{not json")).toBeNull();
    expect(parseStreamEvent("mystery", "{}")).toBeNull();
  });
});
