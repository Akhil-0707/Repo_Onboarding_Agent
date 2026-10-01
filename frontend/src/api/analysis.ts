import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { repoKeys } from "./repos";
import type { Analysis } from "./types";

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
