import type { JobStep } from "../api/types";

/** Model time a tour usually takes on Qwen3-8B (measured 174-239 s). */
export const TOUR_TYPICAL_S = 210;

export const TOUR_STAGES = [
  { key: "research", label: "Reading the code" },
  { key: "writing", label: "Writing the tour stops" },
  { key: "checking", label: "Checking every file and line" },
] as const;

export type TourStage = (typeof TOUR_STAGES)[number]["key"];

/** The bar never claims a stage the job has not reached: each stage has a ceiling. */
const CEILING: Record<TourStage, number> = { research: 0.55, writing: 0.88, checking: 0.97 };

export interface TourProgressView {
  /** 0-2 for the stages, 3 once the tour is written. */
  stage: number;
  /** 0-1, for the progress bar. */
  fraction: number;
  /** What is happening right now, in a few words. */
  activity: string;
  waiting: boolean;
}

/** Turns the job's analyze step into what the progress card shows. Real progress wins; between
 * events (the model writes the stops silently for a minute or two) a time estimate keeps the bar
 * moving, capped below the next stage. */
export function tourProgress(step: JobStep | undefined, elapsedS: number): TourProgressView {
  if (step?.status === "done") {
    return { stage: TOUR_STAGES.length, fraction: 1, activity: "Done", waiting: false };
  }
  const phase: TourStage = step?.phase ?? "research";
  const stage = TOUR_STAGES.findIndex((s) => s.key === phase);
  const real = (step?.progress ?? 0) / 100;
  const estimate = Math.min(CEILING[phase], (elapsedS / TOUR_TYPICAL_S) * 0.95);
  const fraction = Math.max(0.04, real, estimate);

  // Research logs read like "Guided Tour: Reading 'lib/command.js'": show the latest one.
  const lastTool = step?.logs
    .map((entry) => entry.message)
    .filter((message) => message.startsWith("Guided Tour: "))
    .at(-1);
  const activity =
    phase === "research"
      ? (lastTool?.slice("Guided Tour: ".length) ?? "Looking around the code…")
      : phase === "writing"
        ? "The model is writing the stops; this is the longest part."
        : "Verifying each referenced file and line range against the code.";
  return { stage, fraction, activity, waiting: step?.status === "waiting" };
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
