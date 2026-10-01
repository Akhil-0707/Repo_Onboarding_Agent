import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { streamSSE } from "../lib/sse";
import { ApiError, apiFetch } from "./client";
import { repoKeys } from "./repos";
import type { Paginated } from "./types";

export interface ChatCitation {
  path: string;
  start_line: number | null;
  end_line: number | null;
}

export interface ToolStep {
  id: number;
  name: string;
  summary: string;
  ok?: boolean;
  duration_ms?: number;
  arguments?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "complete" | "error";
  error: string;
  citations: ChatCitation[];
  tool_steps: ToolStep[];
  created_at: string;
}

export interface Thread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadDetail extends Thread {
  messages: ChatMessage[];
}

export const chatKeys = {
  threads: (repoId: string) => [...repoKeys.detail(repoId), "threads"] as const,
  thread: (repoId: string, threadId: string) =>
    [...repoKeys.detail(repoId), "threads", threadId] as const,
};

export function useThreads(repoId: string) {
  return useQuery({
    queryKey: chatKeys.threads(repoId),
    queryFn: () => apiFetch<Paginated<Thread>>(`/api/repos/${repoId}/threads?page_size=50`),
  });
}

export function useThread(repoId: string, threadId: string | null) {
  return useQuery({
    queryKey: chatKeys.thread(repoId, threadId ?? ""),
    queryFn: () => apiFetch<ThreadDetail>(`/api/repos/${repoId}/threads/${threadId}`),
    enabled: Boolean(threadId),
  });
}

export function useCreateThread(repoId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<Thread>(`/api/repos/${repoId}/threads`, { method: "POST", body: "{}" }),
    onSuccess: (thread) => {
      queryClient.setQueryData(chatKeys.thread(repoId, thread.id), { ...thread, messages: [] });
      void queryClient.invalidateQueries({ queryKey: chatKeys.threads(repoId), exact: true });
    },
  });
}

export function useDeleteThread(repoId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) =>
      apiFetch<void>(`/api/repos/${repoId}/threads/${threadId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.threads(repoId) }),
  });
}

export interface AskHandlers {
  onStart: (question: ChatMessage) => void;
  onToolStart: (step: ToolStep) => void;
  onToolEnd: (step: ToolStep) => void;
  onToken: (text: string) => void;
  /** The text streamed so far was not the answer (e.g. it preceded tool calls): drop it. */
  onRetract: () => void;
  onDone: (answer: ChatMessage) => void;
  onError: (code: string, message: string) => void;
}

/** Ask a question; resolves when the answer stream ends. HTTP errors reject with ApiError. */
export async function askQuestion(
  repoId: string,
  threadId: string,
  content: string,
  handlers: AskHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let finished = false;
  await streamSSE(`/api/repos/${repoId}/threads/${threadId}/messages/stream`, {
    method: "POST",
    body: { content },
    signal,
    onMessage: ({ event, data }) => {
      const payload = JSON.parse(data) as Record<string, unknown>;
      switch (event) {
        case "start":
          handlers.onStart(payload.message as ChatMessage);
          break;
        case "tool_start":
          handlers.onToolStart(payload as unknown as ToolStep);
          break;
        case "tool_end":
          handlers.onToolEnd(payload as unknown as ToolStep);
          break;
        case "token":
          handlers.onToken(String(payload.text ?? ""));
          break;
        case "retract":
          handlers.onRetract();
          break;
        case "done":
          finished = true;
          handlers.onDone(payload.message as ChatMessage);
          break;
        case "error":
          finished = true;
          handlers.onError(String(payload.code), String(payload.message));
          break;
      }
    },
  });
  if (!finished && !signal?.aborted) {
    throw new ApiError(
      0,
      "stream_interrupted",
      "The connection closed before the answer finished.",
    );
  }
}
