import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import {
  askQuestion,
  chatKeys,
  useCreateThread,
  useDeleteThread,
  useThread,
  useThreads,
} from "../../api/chat";
import type { ChatCitation, ChatMessage, ThreadDetail, ToolStep } from "../../api/chat";
import { useLLMHealth } from "../../api/health";
import { useLineReveal } from "../../hooks/useLineReveal";
import type { CodeRef } from "../../lib/refs";
import { sound } from "../../lib/sound";
import { AnswerText } from "./AnswerText";
import { ToolSteps } from "./ToolSteps";

const NEW = "new";

interface Pending {
  question: string;
  started: boolean;
  steps: ToolStep[];
  draft: string;
  /** The saved answer: shown once the smooth reveal has caught up with it. */
  final: ChatMessage | null;
}

/** How long the answer box takes to ease open to new lines (matches `duration-300`). */
const UNROLL_MS = 320;

/** Three soft dots while the model is thinking. */
function ThinkingDots() {
  return (
    <span role="status" aria-label="Thinking" className="inline-flex items-center gap-1 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          aria-hidden="true"
          className="animate-dot h-1.5 w-1.5 rounded-full bg-slate-400 dark:bg-slate-500"
          style={{ animationDelay: `${i * 160}ms` }}
        />
      ))}
    </span>
  );
}

/** The answer as it streams: rendered like the final answer (no jump at the end) and shown one
 * complete line or sentence at a time; `onRevealed` fires once the whole answer is shown. */
function StreamingAnswer({
  text,
  citations,
  done,
  onOpen,
  onRevealed,
}: {
  text: string;
  citations: ChatCitation[];
  done: boolean;
  onOpen: (ref: CodeRef) => void;
  onRevealed: () => void;
}) {
  const { text: shown, caughtUp } = useLineReveal(text, done);
  const inner = useRef<HTMLDivElement | null>(null);
  const [height, setHeight] = useState<number>();
  const visible = Boolean(shown) || caughtUp;

  useEffect(() => {
    if (!caughtUp) return;
    const timer = window.setTimeout(onRevealed, UNROLL_MS); // let the last lines unroll first
    return () => window.clearTimeout(timer);
  }, [caughtUp, onRevealed]);

  // The box eases open to its content, so new lines are uncovered from the top, one by one.
  useEffect(() => {
    const element = inner.current;
    if (!visible || !element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, [visible]);

  // Until the first line or sentence is complete, keep the thinking dots.
  if (!visible) return <ThinkingDots />;
  return (
    <div
      className="overflow-hidden transition-[height] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]"
      style={{ height }}
    >
      <div ref={inner}>
        <AnswerText text={shown} citations={citations} onOpen={onOpen} animate />
      </div>
    </div>
  );
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
  const scroller = useRef<HTMLDivElement | null>(null);
  const content = useRef<HTMLDivElement | null>(null);
  /** Follow new text only while the reader is at the bottom; scrolling up to read stops it. */
  const stick = useRef(true);
  /** Completes a finished answer once its reveal has caught up. */
  const finish = useRef<(() => void) | null>(null);
  /** A short answer can be fully revealed before the stream has closed. */
  const revealed = useRef(false);

  // While an answer is still being revealed, a refetched thread may already contain it.
  const messages = (thread.data?.messages ?? []).filter((m) => m.id !== pending?.final?.id);

  const send = async (raw: string) => {
    const content = raw.trim();
    if (!content || pending || offline) return;
    setError(null);
    setInput("");
    setPending({ question: content, started: false, steps: [], draft: "", final: null });
    stick.current = true;
    revealed.current = false;
    const controller = new AbortController();
    abort.current = controller;
    let id = threadId;
    let started = false;
    let final: ChatMessage | null = null;
    const append = (message: ChatMessage) => {
      if (!id) return;
      queryClient.setQueryData<ThreadDetail>(chatKeys.thread(repoId, id), (old) =>
        old && !old.messages.some((m) => m.id === message.id)
          ? { ...old, messages: [...old.messages, message] }
          : old,
      );
    };
    try {
      if (!id) {
        const created = await createThread.mutateAsync();
        id = created.id;
        setSelected(created.id);
      }
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
          onDone: (message) => {
            final = message;
            setPending((p) => p && { ...p, final: message });
          },
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
      const settle = () => {
        finish.current = null;
        if (final) append(final);
        setPending(null);
        if (id) void queryClient.invalidateQueries({ queryKey: chatKeys.thread(repoId, id) });
        void queryClient.invalidateQueries({ queryKey: chatKeys.threads(repoId), exact: true });
      };
      const complete = () => {
        sound.answerReady();
        settle();
      };
      // A complete answer finishes when its reveal catches up (see StreamingAnswer).
      if (!final || controller.signal.aborted) settle();
      else if (revealed.current) complete();
      else finish.current = complete;
    }
  };

  const onRevealed = useCallback(() => {
    if (finish.current) finish.current();
    else revealed.current = true; // the stream closes right after: complete it then
  }, []);

  useEffect(() => {
    if (autoAsk && !autoAsked.current) {
      autoAsked.current = true;
      void send(autoAsk);
    }
    // Mount only: autoAsk is consumed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => abort.current?.abort(), []);

  // Keep the newest text in view while it grows (every revealed frame changes the height).
  useEffect(() => {
    const box = scroller.current;
    const inner = content.current;
    if (!box || !inner || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (stick.current) box.scrollTop = box.scrollHeight;
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, []);

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

      <div
        ref={scroller}
        onScroll={(event) => {
          const box = event.currentTarget;
          stick.current = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        }}
        className="min-h-0 flex-1 overflow-auto px-3 py-3"
        aria-live="polite"
      >
        <div ref={content}>
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
                  <div className="animate-fade-up mr-4" aria-busy={!pending.final}>
                    <ToolSteps steps={pending.steps} live={!pending.final} />
                    {pending.final || pending.draft ? (
                      <StreamingAnswer
                        text={pending.final?.content ?? pending.draft}
                        citations={pending.final?.citations ?? []}
                        done={Boolean(pending.final)}
                        onOpen={onOpen}
                        onRevealed={onRevealed}
                      />
                    ) : (
                      <ThinkingDots />
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
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
