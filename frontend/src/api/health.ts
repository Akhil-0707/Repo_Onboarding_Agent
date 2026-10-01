import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface LLMHealth {
  online: boolean;
  model: string;
  latency_ms: number | null;
  checked_at: string;
  error: string | null;
}

export const LLM_HEALTH_POLL_MS = 30_000;

export function fetchLLMHealth(): Promise<LLMHealth> {
  return apiFetch<LLMHealth>("/api/llm/health");
}

export function useLLMHealth() {
  return useQuery({
    queryKey: ["llm-health"],
    queryFn: fetchLLMHealth,
    refetchInterval: LLM_HEALTH_POLL_MS,
    retry: false,
  });
}
