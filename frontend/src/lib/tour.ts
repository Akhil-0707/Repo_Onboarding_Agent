import type { TourStepKind } from "../api/types";

export const TOUR_KIND_LABELS: Record<TourStepKind, string> = {
  intro: "Intro",
  entry_point: "Entry point",
  flow_trace: "Flow trace",
  core_logic: "Core logic",
  data_model: "Data model",
  config: "Configuration",
  testing: "Testing",
  other: "Detail",
};

/** `?step=` is 1-based in the URL; returns a 0-based index clamped to the tour. */
export function parseStep(raw: string | null, total: number): number {
  const value = Number.parseInt(raw ?? "", 10);
  if (!Number.isFinite(value) || total === 0) return 0;
  return Math.min(Math.max(value, 1), total) - 1;
}
