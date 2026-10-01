import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer } from "react";

import { repoKeys } from "../api/repos";
import type { Job, JobStatus, JobStep, LogEntry } from "../api/types";
import { streamSSE } from "../lib/sse";

export type StreamEvent =
  | { type: "snapshot"; job: Job }
  | { type: "step"; key: string; fields: Partial<JobStep>; jobProgress?: number }
  | { type: "log"; key: string; entry: LogEntry }
  | { type: "job"; status: JobStatus; error?: string }
  | { type: "end" };

export interface JobStreamState {
  job: Job | null;
  ended: boolean;
  connected: boolean;
  error: string | null;
}

type Action = StreamEvent | { type: "connected" } | { type: "error"; message: string };

const TERMINAL = new Set<JobStatus>(["done", "failed"]);

export function jobReducer(state: JobStreamState, action: Action): JobStreamState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true, error: null };
    case "error":
      return { ...state, connected: false, error: action.message };
    case "snapshot":
      return { ...state, job: action.job, ended: TERMINAL.has(action.job.status) };
    case "end":
      return { ...state, ended: true };
    case "job":
      if (!state.job) return state;
      return {
        ...state,
        job: {
          ...state.job,
          status: action.status,
          error: action.error ?? state.job.error,
          progress: action.status === "done" ? 100 : state.job.progress,
        },
      };
    case "step":
    case "log": {
      if (!state.job) return state;
      const steps = state.job.steps.map((step) => {
        if (step.key !== action.key) return step;
        if (action.type === "log")
          return { ...step, logs: [...step.logs, action.entry].slice(-200) };
        return { ...step, ...action.fields };
      });
      const progress =
        action.type === "step" && action.jobProgress !== undefined
          ? action.jobProgress
          : state.job.progress;
      return { ...state, job: { ...state.job, steps, progress } };
    }
  }
}

export function parseStreamEvent(event: string, data: string): StreamEvent | null {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
  switch (event) {
    case "snapshot":
      return { type: "snapshot", job: payload as unknown as Job };
    case "end":
      return { type: "end" };
    case "job":
      return {
        type: "job",
        status: payload.status as JobStatus,
        error: payload.error as string | undefined,
      };
    case "log":
      return {
        type: "log",
        key: String(payload.key),
        entry: {
          ts: String(payload.ts),
          level: (payload.level as LogEntry["level"]) ?? "info",
          message: String(payload.message ?? ""),
        },
      };
    case "step": {
      const { type: _type, key, job_progress, ...fields } = payload;
      return {
        type: "step",
        key: String(key),
        fields: fields as Partial<JobStep>,
        jobProgress: typeof job_progress === "number" ? job_progress : undefined,
      };
    }
    default:
      return null;
  }
}

const RECONNECT_DELAYS = [1000, 2000, 5000, 10000];

/** Live ingestion progress for a repository, reconnecting until the job finishes. */
export function useJobStream(repoId: string, attempt = 0): JobStreamState {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(jobReducer, {
    job: null,
    ended: false,
    connected: false,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    let attempt = 0;
    let finished = false;

    async function run() {
      while (!controller.signal.aborted && !finished) {
        try {
          await streamSSE(`/api/repos/${repoId}/job/stream`, {
            signal: controller.signal,
            onMessage: ({ event, data }) => {
              const parsed = parseStreamEvent(event, data);
              if (!parsed) return;
              attempt = 0;
              dispatch(parsed);
              if (parsed.type === "end") finished = true;
            },
          });
          dispatch({ type: "connected" });
        } catch (error) {
          if (controller.signal.aborted) return;
          const status = (error as { status?: number }).status;
          dispatch({
            type: "error",
            message: error instanceof Error ? error.message : "Connection lost",
          });
          if (status === 401 || status === 403 || status === 404) return;
        }
        if (finished || controller.signal.aborted) break;
        const delay = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)];
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
      if (finished) {
        void queryClient.invalidateQueries({ queryKey: repoKeys.detail(repoId) });
        void queryClient.invalidateQueries({ queryKey: repoKeys.list() });
      }
    }

    void run();
    return () => controller.abort();
  }, [repoId, attempt, queryClient]);

  return state;
}
