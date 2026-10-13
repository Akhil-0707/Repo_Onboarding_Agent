import { useGenerateSection } from "../../api/analysis";
import { useLLMHealth } from "../../api/health";
import type { AnalysisStatus } from "../../api/types";

/** Shown in place of the Guided Tour until someone asks for it: it is the slowest section, so
 * analyses skip it and it is written on request (then shared with everyone). */
export function TourRequest({
  repoId,
  analysisStatus,
}: {
  repoId: string;
  analysisStatus: AnalysisStatus | undefined;
}) {
  const generate = useGenerateSection(repoId, "tour");
  const health = useLLMHealth();
  const busy =
    analysisStatus === "pending" ||
    analysisStatus === "running" ||
    analysisStatus === "waiting_for_model";

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="surface animate-fade-up p-6">
        <p className="eyebrow">Guided tour</p>
        <h2 className="mt-2 text-xl font-semibold tracking-tight">
          Walk through the code step by step
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          A tour of 8 to 12 stops from the entry point through one real flow, each with the exact
          lines to read. Creating it reads through the code and{" "}
          <strong className="font-semibold text-slate-900 dark:text-white">
            takes about 3 to 4 minutes
          </strong>
          . You can keep browsing meanwhile; it appears here when it is ready.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? "Starting…" : "Create the guided tour"}
          </button>
          {busy && (
            <span className="text-sm text-slate-500 dark:text-slate-400">
              Available once the current analysis finishes.
            </span>
          )}
          {!busy && health.data?.online === false && (
            <span className="text-sm text-amber-700 dark:text-amber-300">
              The AI model is offline: the tour will be written once it is back.
            </span>
          )}
        </div>
        {generate.isError && (
          <p role="alert" className="mt-3 text-sm text-rose-600 dark:text-rose-400">
            {generate.error.message}
          </p>
        )}
      </div>
    </div>
  );
}
