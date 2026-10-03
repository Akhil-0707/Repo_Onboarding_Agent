import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { repoKeys } from "./repos";
import type { AnalysisStart } from "./types";

export interface UsageTotals {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  est_cost: number;
}

export interface ChatUsage extends UsageTotals {
  questions: number;
}

export interface Pricing {
  input_per_1k: number;
  output_per_1k: number;
  self_hosted: boolean;
}

export interface Quota {
  limit: number;
  used: number;
  remaining: number;
  reset_in_seconds: number;
  window_seconds: number;
}

export interface UserUsage {
  totals: { analysis: UsageTotals; chat: ChatUsage; all: UsageTotals };
  repositories: {
    id: string;
    full_name: string;
    commit_sha: string;
    on_dashboard: boolean;
    started_by_you: boolean;
    analysis: UsageTotals | null;
    chat: ChatUsage | null;
  }[];
  rate_limit: { new_analyses: Quota };
  pricing: Pricing;
}

export const usageKeys = { mine: ["usage"] as const };

export function useUserUsage() {
  return useQuery({
    queryKey: usageKeys.mine,
    queryFn: () => apiFetch<UserUsage>("/api/usage"),
  });
}

export function formatCost(cost: number, pricing: Pricing): string {
  if (pricing.self_hosted) return "≈$0 (self-hosted)";
  return cost < 0.01 ? `≈$${cost.toFixed(4)}` : `≈$${cost.toFixed(2)}`;
}

/** Analyse the latest commit, or retry unfinished AI sections of this one. */
export function useReanalyze(repoId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<AnalysisStart>(`/api/repos/${repoId}/reanalyze`, { method: "POST" }),
    onSuccess: (result) => {
      queryClient.setQueryData(repoKeys.detail(result.repository.id), result.repository);
      void queryClient.invalidateQueries({ queryKey: repoKeys.detail(repoId) });
      void queryClient.invalidateQueries({ queryKey: repoKeys.list() });
      void queryClient.invalidateQueries({ queryKey: usageKeys.mine });
    },
  });
}
