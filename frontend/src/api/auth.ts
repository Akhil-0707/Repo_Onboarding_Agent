import { API_BASE, apiFetch } from "./client";

export interface User {
  id: string;
  username: string;
  name: string;
  email: string;
  avatar_url: string;
  github_connected: boolean;
  private_repo_access: boolean;
  date_joined: string;
}

export interface SessionResponse {
  access: string;
  user: User;
}

export function githubLoginUrl({
  next,
  privateRepos = false,
}: { next?: string; privateRepos?: boolean } = {}): string {
  const params = new URLSearchParams();
  if (next) params.set("next", next);
  if (privateRepos) params.set("private", "1");
  const query = params.toString();
  return `${API_BASE}/api/auth/github/login${query ? `?${query}` : ""}`;
}

export function exchangeCode(code: string): Promise<SessionResponse> {
  return apiFetch<SessionResponse>("/api/auth/exchange", {
    method: "POST",
    body: JSON.stringify({ code }),
    skipAuthRetry: true,
  });
}

export function refreshSession(): Promise<SessionResponse> {
  return apiFetch<SessionResponse>("/api/auth/refresh", { method: "POST", skipAuthRetry: true });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/api/auth/logout", { method: "POST", skipAuthRetry: true });
}
