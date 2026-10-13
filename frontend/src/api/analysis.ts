import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { repoKeys } from "./repos";
import type { Analysis, AnalysisStart } from "./types";

const ACTIVE = new Set(["pending", "running", "waiting_for_model"]);

export function useAnalysis(repoId: string, enabled = true) {
  return useQuery({
    queryKey: [...repoKeys.detail(repoId), "analysis"],
    queryFn: () => apiFetch<Analysis>(`/api/repos/${repoId}/analysis`),
    enabled,
    // Poll while the agent is still writing (or waiting for the model to come back).
    refetchInterval: (query) =>
      query.state.data && ACTIVE.has(query.state.data.status) ? 4000 : false,
  });
}

/** Asks for an on-demand section (the Guided Tour); the analysis query then polls until done. */
export function useGenerateSection(repoId: string, section: "tour") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<AnalysisStart>(`/api/repos/${repoId}/analysis/${section}/generate`, {
        method: "POST",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: repoKeys.detail(repoId) });
      void queryClient.invalidateQueries({ queryKey: repoKeys.list() });
    },
  });
}
