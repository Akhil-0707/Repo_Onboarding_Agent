import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import {
  askQuestion,
  chatKeys,
  useCreateThread,
  useDeleteThread,
  useThread,
  useThreads,
} from "../../api/chat";
import type { ChatMessage, ThreadDetail, ToolStep } from "../../api/chat";
import { useLLMHealth } from "../../api/health";
import type { CodeRef } from "../../lib/refs";
import { Spinner } from "../StateViews";
import { AnswerText } from "./AnswerText";
import { ToolSteps } from "./ToolSteps";

const NEW = "new";

interface Pending {
  question: string;
  started: boolean;
  steps: ToolStep[];
  draft: string;
}

function MessageView({
  message,
  onOpen,
}: {
  message: ChatMessage;
  onOpen: (ref: CodeRef) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="bg-brand animate-fade-up ml-8 self-end rounded-2xl rounded-br-md px-3.5 py-2 text-sm whitespace-pre-wrap">
        {message.content}
      </div>
    );
  }
  return (
    <div className="animate-fade-up mr-4">
      <ToolSteps steps={message.tool_steps} />
      {message.status === "error" ? (
        <p
          role="alert"
          className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200/70 dark:bg-amber-400/[0.06] dark:text-amber-200 dark:ring-amber-400/20"
        >
          {message.error}
        </p>
      ) : (
        <AnswerText text={message.content} citations={message.citations} onOpen={onOpen} />
      )}
    </div>
  );
}

export function ChatPanel({
  repoId,
  starterQuestions,
  onOpen,
  autoAsk,
}: {
  repoId: string;
  starterQuestions: string[];
  onOpen: (ref: CodeRef) => void;
  /** Asked once when the panel mounts (e.g. a starter question clicked elsewhere). */
  autoAsk?: string;
}) {
  const queryClient = useQueryClient();
  const health = useLLMHealth();
  const offline = health.data?.online === false;
  const threads = useThreads(repoId);
  const [selected, setSelected] = useState<string | null>(autoAsk ? NEW : null);
  const threadId = selected === NEW ? null : (selected ?? threads.data?.results[0]?.id ?? null);
  const thread = useThread(repoId, threadId);
  const createThread = useCreateThread(repoId);
  const deleteThread = useDeleteThread(repoId);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const autoAsked = useRef(false);
  const bottom = useRef<HTMLDivElement | null>(null);

  const messages = thread.data?.messages ?? [];

  const send = async (raw: string) => {
    const content = raw.trim();
    if (!content || pending || offline) return;
    setError(null);
    setInput("");
    setPending({ question: content, started: false, steps: [], draft: "" });
    const controller = new AbortController();
    abort.current = controller;
    let id = threadId;
    let started = false;
    try {
      if (!id) {
        const created = await createThread.mutateAsync();
        id = created.id;
        setSelected(created.id);
      }
      const key = chatKeys.thread(repoId, id);
      const append = (message: ChatMessage) =>
        queryClient.setQueryData<ThreadDetail>(key, (old) =>
          old ? { ...old, messages: [...old.messages, message] } : old,
        );
      await askQuestion(
        repoId,
        id,
        content,
        {
          onStart: (question) => {
            started = true;
            append(question);
            setPending((p) => p && { ...p, started: true });
          },
          onToolStart: (step) =>
            setPending((p) => p && { ...p, draft: "", steps: [...p.steps, step] }),
          onToolEnd: (step) =>
            setPending(
              (p) => p && { ...p, steps: p.steps.map((s) => (s.id === step.id ? step : s)) },
            ),
          onToken: (text) => setPending((p) => p && { ...p, draft: p.draft + text }),
          onRetract: () => setPending((p) => p && { ...p, draft: "" }),
          onDone: append,
          onError: (_code, message) => setError(message),
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "The question could not be sent.");
        if (!started) setInput(content); // nothing was saved: give the text back
      }
    } finally {
      abort.current = null;
      setPending(null);
      if (id) void queryClient.invalidateQueries({ queryKey: chatKeys.thread(repoId, id) });
      void queryClient.invalidateQueries({ queryKey: chatKeys.threads(repoId), exact: true });
    }
  };

  useEffect(() => {
    if (autoAsk && !autoAsked.current) {
      autoAsked.current = true;
      void send(autoAsk);
    }
    // Mount only: autoAsk is consumed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, pending?.draft, pending?.steps.length]);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  };

  const removeThread = async () => {
    if (!threadId || !window.confirm("Delete this conversation?")) return;
    await deleteThread.mutateAsync(threadId);
    setSelected(null);
  };

  const empty = messages.length === 0 && !pending;
  const threadList = threads.data?.results ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-slate-900/[0.06] px-3 py-2 dark:border-white/[0.06]">
        <label htmlFor="chat-thread" className="sr-only">
          Conversation
        </label>
        <select
          id="chat-thread"
          value={threadId ?? NEW}
          onChange={(event) => setSelected(event.target.value)}
          disabled={Boolean(pending)}
          className="min-w-0 flex-1 truncate rounded-lg bg-slate-900/[0.05] px-2 py-1.5 text-sm ring-1 ring-slate-900/[0.06] dark:bg-white/[0.06] dark:ring-white/[0.08]"
        >
          {threadId === null && <option value={NEW}>New conversation</option>}
          {threadList.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title || "Untitled conversation"}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setSelected(NEW)}
          disabled={Boolean(pending) || threadId === null}
          className="btn btn-ghost px-2.5 py-1.5"
        >
          New
        </button>
        <button
          type="button"
          onClick={() => void removeThread()}
          disabled={Boolean(pending) || threadId === null}
          aria-label="Delete conversation"
          className="btn btn-ghost px-2.5 py-1.5"
        >
          🗑
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-3" aria-live="polite">
        {empty ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-slate-500">
              Ask anything about this codebase. Answers cite the exact files and lines they are
              based on.
            </p>
            {starterQuestions.length > 0 && (
              <ul aria-label="Suggested questions" className="stagger flex flex-col gap-2">
                {starterQuestions.map((question) => (
                  <li key={question}>
                    <button
                      type="button"
                      disabled={offline}
                      onClick={() => void send(question)}
                      className="w-full rounded-xl text-left bg-slate-900/[0.04] px-3.5 py-1.5 text-sm text-slate-700 ring-1 ring-slate-900/[0.06] transition-all duration-300 hover:-translate-y-px hover:bg-slate-900/[0.08] hover:text-slate-900 active:translate-y-0 disabled:cursor-default disabled:opacity-60 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.08] dark:hover:bg-white/10 dark:hover:text-white"
                    >
                      {question}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((message) => (
              <MessageView key={message.id} message={message} onOpen={onOpen} />
            ))}
            {pending && (
              <>
                {!pending.started && (
                  <MessageView
                    message={{
                      id: "pending",
                      role: "user",
                      content: pending.question,
                      status: "complete",
                      error: "",
                      citations: [],
                      tool_steps: [],
                      created_at: "",
                    }}
                    onOpen={onOpen}
                  />
                )}
                <div className="mr-4" aria-busy="true">
                  <ToolSteps steps={pending.steps} live />
                  {pending.draft ? (
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">
                      {pending.draft}
                      <span className="ml-0.5 animate-pulse">▍</span>
                    </p>
                  ) : (
                    <Spinner label="Thinking" />
                  )}
                </div>
              </>
            )}
          </div>
        )}
        <div ref={bottom} />
      </div>

      {error && (
        <p
          role="alert"
          className="animate-fade-in mx-3 mb-2 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:bg-rose-950/30 dark:text-rose-200"
        >
          {error}
        </p>
      )}
      {offline && (
        <p
          role="status"
          className="animate-fade-in mx-3 mb-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-400/[0.06] dark:text-amber-200"
        >
          The AI model is offline. You can read earlier answers; asking is disabled until it is
          back.
        </p>
      )}

      <form
        className="flex items-end gap-2 border-t border-slate-900/[0.06] p-3 dark:border-white/[0.06]"
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
      >
        <label htmlFor="chat-input" className="sr-only">
          Ask a question
        </label>
        <textarea
          id="chat-input"
          rows={2}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={offline || Boolean(pending)}
          placeholder={offline ? "Model offline" : "Ask about the code… (Enter to send)"}
          className="field min-h-10 flex-1 resize-none disabled:opacity-60"
        />
        {pending ? (
          <button
            type="button"
            onClick={() => abort.current?.abort()}
            className="btn btn-secondary"
          >
            Stop
          </button>
        ) : (
          <button type="submit" disabled={offline || !input.trim()} className="btn btn-primary">
            Send
          </button>
        )}
      </form>
    </div>
  );
}
