import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AnalysisStart, FileContent, FileEntry, Job, Paginated, Repository } from "./types";

export const repoKeys = {
  all: ["repos"] as const,
  list: () => [...repoKeys.all, "list"] as const,
  detail: (id: string) => [...repoKeys.all, id] as const,
  job: (id: string) => [...repoKeys.all, id, "job"] as const,
  tree: (id: string) => [...repoKeys.all, id, "tree"] as const,
  file: (id: string, path: string) => [...repoKeys.all, id, "file", path] as const,
};

const ACTIVE = new Set(["queued", "ingesting", "waiting_for_model"]);

export function useRepositories() {
  return useQuery({
    queryKey: repoKeys.list(),
    queryFn: () => apiFetch<Paginated<Repository>>("/api/repos?page_size=100"),
    // Keep dashboard badges fresh while anything is still processing.
    refetchInterval: (query) =>
      query.state.data?.results.some((repo) => ACTIVE.has(repo.status)) ? 5000 : false,
  });
}

export function useRepository(id: string) {
  return useQuery({
    queryKey: repoKeys.detail(id),
    queryFn: () => apiFetch<Repository>(`/api/repos/${id}`),
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: repoKeys.job(id),
    queryFn: () => apiFetch<Job>(`/api/repos/${id}/job`),
  });
}

export function useTree(id: string, enabled = true) {
  return useQuery({
    queryKey: repoKeys.tree(id),
    queryFn: () => apiFetch<{ files: FileEntry[]; commit_sha: string }>(`/api/repos/${id}/tree`),
    enabled,
    staleTime: Infinity, // a snapshot never changes
  });
}

export function useFileContent(id: string, path: string | null) {
  return useQuery({
    queryKey: repoKeys.file(id, path ?? ""),
    queryFn: () =>
      apiFetch<FileContent>(`/api/repos/${id}/files?path=${encodeURIComponent(path ?? "")}`),
    enabled: Boolean(path),
    staleTime: Infinity,
  });
}

export function useStartAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (url: string) =>
      apiFetch<AnalysisStart>("/api/repos", { method: "POST", body: JSON.stringify({ url }) }),
    onSuccess: (result) => {
      queryClient.setQueryData(repoKeys.detail(result.repository.id), result.repository);
      void queryClient.invalidateQueries({ queryKey: repoKeys.list() });
    },
  });
}

export function useRemoveRepository() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/repos/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: repoKeys.list() }),
  });
}
