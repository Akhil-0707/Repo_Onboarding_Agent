import type { Repository } from "../api/types";

/** Only same-site relative paths are allowed as post-login destinations. */
export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/dashboard";
  }
  return value;
}

/** Where a repository card should lead: the workspace when ready, progress otherwise. */
export function repoHref(repo: Pick<Repository, "id" | "status">): string {
  return repo.status === "ready" ? `/repos/${repo.id}` : `/repos/${repo.id}/progress`;
}
