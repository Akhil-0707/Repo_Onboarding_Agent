import type { ReactNode } from "react";

import type { AnalysisStatus, SectionState } from "../../api/types";
import { EmptyState, ErrorState, Skeleton } from "../StateViews";

/** Shared loading / waiting / failed / empty handling for every AI-generated section. */
export function SectionShell<T>({
  title,
  section,
  analysisStatus,
  children,
}: {
  title: string;
  section: SectionState<T> | undefined;
  analysisStatus: AnalysisStatus | undefined;
  children: (data: T) => ReactNode;
}) {
  if (section?.status === "done" && section.data) {
    return <>{children(section.data)}</>;
  }
  if (section?.status === "failed") {
    return (
      <div className="p-6">
        <ErrorState
          title={`${title} could not be generated`}
          message={section.error || "The model did not return usable output."}
        />
      </div>
    );
  }
  if (analysisStatus === "waiting_for_model") {
    return (
      <div className="p-6">
        <div
          role="status"
          className="animate-fade-up mx-auto max-w-3xl rounded-2xl bg-amber-50 p-5 text-amber-900 ring-1 ring-amber-200/70 dark:bg-amber-400/[0.06] dark:text-amber-200 dark:ring-amber-400/20"
        >
          <h3 className="font-semibold">Waiting for the AI model</h3>
          <p className="mt-1 text-sm">
            The model server is offline. The analysis is paused and will resume automatically from
            where it stopped. You can browse the code in the meantime.
          </p>
        </div>
      </div>
    );
  }
  if (analysisStatus === "failed" || analysisStatus === "done" || analysisStatus === "partial") {
    return (
      <div className="p-6">
        <EmptyState title={`No ${title.toLowerCase()} yet`} />
      </div>
    );
  }
  return (
    <div
      className="animate-fade-in mx-auto flex max-w-5xl flex-col gap-3 px-6 py-8"
      aria-busy="true"
    >
      <p className="text-sm text-slate-500" role="status">
        {section?.status === "running"
          ? `Writing the ${title.toLowerCase()}…`
          : "Queued for the AI analysis…"}
      </p>
      <Skeleton className="h-5 w-1/2" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}
