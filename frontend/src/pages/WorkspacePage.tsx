import { useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router";

import { useAnalysis } from "../api/analysis";
import { useRepository, useTree } from "../api/repos";
import { useReanalyze } from "../api/usage";
import type { Repository } from "../api/types";
import { ChatPanel } from "../components/chat/ChatPanel";
import { CodeViewer } from "../components/CodeViewer";
import type { LineRange } from "../components/CodeViewer";
import { FileTree } from "../components/FileTree";
import { LanguageBar } from "../components/LanguageBar";
import { ArchitectureSection } from "../components/sections/ArchitectureSection";
import { GlossarySection } from "../components/sections/GlossarySection";
import { OverviewSection } from "../components/sections/OverviewSection";
import { SectionShell } from "../components/sections/SectionShell";
import { StartHereSection } from "../components/sections/StartHereSection";
import { TourSection } from "../components/sections/TourSection";
import { StatusBadge } from "../components/StatusBadge";
import { ErrorState, LoadingState } from "../components/StateViews";
import { formatRange, parseRange } from "../lib/range";
import type { CodeRef } from "../lib/refs";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "architecture", label: "Architecture" },
  { key: "start-here", label: "Start Here" },
  { key: "tour", label: "Tour" },
  { key: "glossary", label: "Glossary" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** Side panels sit next to the content from `lg` up; below that they overlay it. */
function isWide(): boolean {
  return window.matchMedia?.("(min-width: 1024px)").matches ?? true;
}

function Stat({
  label,
  value,
  index,
}: {
  label: string;
  value: number | undefined;
  index: number;
}) {
  return (
    <div
      className="surface surface-hover animate-fade-up p-4"
      style={{ animationDelay: `${index * 75}ms` }}
    >
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tracking-tight tabular-nums">
        {value?.toLocaleString() ?? "—"}
      </dd>
    </div>
  );
}

function SidebarIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      className="h-[18px] w-[18px]"
      aria-hidden="true"
    >
      <rect x="2.75" y="3.75" width="14.5" height="12.5" rx="2.25" />
      <path d="M7.5 3.75v12.5" />
    </svg>
  );
}

/** Section tabs with an underline that glides to the active tab. */
function TabBar({ active, onSelect }: { active: TabKey; onSelect: (key: TabKey) => void }) {
  const refs = useRef<Partial<Record<TabKey, HTMLButtonElement | null>>>({});
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const measure = () => {
      const el = refs.current[active];
      if (el) setIndicator({ left: el.offsetLeft, width: el.offsetWidth });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [active]);

  return (
    <nav
      role="tablist"
      aria-label="Onboarding sections"
      className="relative flex gap-1 overflow-x-auto border-b border-slate-900/[0.06] px-4 dark:border-white/[0.06]"
    >
      {TABS.map((item) => (
        <button
          key={item.key}
          ref={(el) => {
            refs.current[item.key] = el;
          }}
          role="tab"
          type="button"
          aria-selected={active === item.key}
          onClick={() => onSelect(item.key)}
          className={`px-3 py-3 text-sm font-medium whitespace-nowrap transition-colors duration-300 ${
            active === item.key
              ? "text-slate-900 dark:text-white"
              : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          }`}
        >
          {item.label}
        </button>
      ))}
      {indicator && (
        <span
          aria-hidden="true"
          className="bg-brand absolute bottom-0 left-0 h-0.5 rounded-full transition-[transform,width] duration-450 ease-[cubic-bezier(0.22,1,0.36,1)]"
          style={{ width: indicator.width, transform: `translateX(${indicator.left}px)` }}
        />
      )}
    </nav>
  );
}

function IndexSummary({ repo }: { repo: Repository }) {
  const scripts = Object.entries(repo.detection.scripts ?? {}).slice(0, 8);
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 border-t border-slate-900/[0.06] px-6 py-8 dark:border-white/[0.06]">
      <h2 className="eyebrow">Repository facts</h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat index={0} label="Files" value={repo.stats.files} />
        <Stat index={1} label="Lines" value={repo.stats.lines} />
        <Stat index={2} label="Symbols" value={repo.stats.symbols} />
        <Stat index={3} label="Internal imports" value={repo.stats.dependency_edges} />
      </dl>
      <section>
        <h3 className="mb-2 text-sm font-semibold">Languages</h3>
        <LanguageBar languages={repo.languages} limit={8} />
      </section>
      {repo.frameworks.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Frameworks & tools</h3>
          <ul className="flex flex-wrap gap-2">
            {repo.frameworks.map((framework) => (
              <li
                key={framework}
                className="rounded-full bg-slate-900/[0.05] px-2.5 py-0.5 text-sm dark:bg-white/[0.07]"
              >
                {framework}
              </li>
            ))}
          </ul>
        </section>
      )}
      {scripts.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Scripts found in manifests</h3>
          <ul className="font-mono text-sm">
            {scripts.map(([name, command]) => (
              <li key={name}>
                <span className="font-medium text-slate-900 dark:text-slate-100">{name}</span>
                {command && <span className="text-slate-500"> — {command}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function WorkspacePage() {
  const { repoId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const repo = useRepository(repoId);
  const ready = repo.data?.status === "ready";
  const tree = useTree(repoId, ready);
  const analysis = useAnalysis(repoId, ready);
  const reanalyze = useReanalyze(repoId);
  const navigate = useNavigate();
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null);
  const [showTree, setShowTree] = useState(isWide);
  const [chatOpen, setChatOpen] = useState(false);
  // A starter question clicked outside the chat: (re)mount the panel and ask it.
  const [chatRequest, setChatRequest] = useState<{ text: string; nonce: number } | null>(null);
  const askInChat = (text: string) => {
    setChatRequest({ text, nonce: Date.now() });
    setChatOpen(true);
  };

  const tab = (params.get("tab") as TabKey | null) ?? "overview";
  const filePath = params.get("file");
  const range = parseRange(params.get("lines"));

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: false });
  };
  const openFile = (path: string, lines: LineRange | null = null) =>
    update({ file: path, lines: formatRange(lines) });
  const openRef = (ref: CodeRef) => {
    if (ref.path.endsWith("/")) return;
    openFile(
      ref.path,
      ref.start_line ? { start: ref.start_line, end: ref.end_line ?? ref.start_line } : null,
    );
  };

  const sectionProps = {
    analysisStatus: analysis.data?.status,
    analysisError: analysis.data?.error,
    onReanalyze: () => runReanalyze(),
    reanalyzing: reanalyze.isPending,
  };
  const runReanalyze = () => {
    setNotice(null);
    reanalyze.mutate(undefined, {
      onSuccess: (result) => {
        if (result.repository.id !== repoId) {
          // A newer commit: open its snapshot (or its progress if work started).
          void navigate(
            result.created
              ? `/repos/${result.repository.id}/progress`
              : `/repos/${result.repository.id}`,
          );
        } else if (result.created) {
          setNotice({
            error: false,
            text: "Re-running the AI sections that did not finish…",
          });
        } else {
          setNotice({
            error: false,
            text: "Already up to date: this is the latest commit and every section is done.",
          });
        }
      },
      onError: (error) => setNotice({ error: true, text: error.message }),
    });
  };

  if (repo.isPending) return <LoadingState label="Loading repository" />;
  if (repo.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <ErrorState title="Repository not found" message={repo.error.message} />
      </div>
    );
  }
  if (!ready) return <Navigate to={`/repos/${repoId}/progress`} replace />;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="flex h-12 items-center gap-2 border-b border-slate-900/[0.06] px-3 sm:gap-3 sm:px-4 dark:border-white/[0.06]">
        <button
          type="button"
          onClick={() => setShowTree((value) => !value)}
          aria-pressed={showTree}
          aria-label={showTree ? "Hide files" : "Show files"}
          title={showTree ? "Hide files" : "Show files"}
          className="btn btn-ghost h-8 w-8 shrink-0 p-0"
        >
          <SidebarIcon />
        </button>
        <Link
          to="/dashboard"
          className="text-sm text-slate-500 transition-colors duration-300 hover:text-slate-900 max-sm:hidden dark:text-slate-400 dark:hover:text-white"
        >
          Dashboard
        </Link>
        <span className="text-slate-300 max-sm:hidden dark:text-slate-700">/</span>
        <h1 className="min-w-0 truncate font-mono text-sm font-semibold">{repo.data.full_name}</h1>
        <a
          href={`${repo.data.url}/tree/${repo.data.commit_sha}`}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-xs text-slate-500 transition-colors duration-300 hover:text-slate-900 max-md:hidden dark:text-slate-400 dark:hover:text-white"
        >
          @{repo.data.commit_sha.slice(0, 7)}
        </a>
        {analysis.data && analysis.data.status !== "done" && (
          <span className="shrink-0 max-sm:hidden">
            <StatusBadge status={analysis.data.status} />
          </span>
        )}
        <button
          type="button"
          disabled={reanalyze.isPending}
          onClick={runReanalyze}
          title="Re-run the AI sections that did not finish, or analyze a newer commit"
          className="btn btn-ghost ml-auto shrink-0 px-3 py-1.5"
        >
          {reanalyze.isPending ? "Checking…" : "Re-analyze"}
        </button>
        <button
          type="button"
          onClick={() => setChatOpen((value) => !value)}
          aria-pressed={chatOpen}
          className={`btn shrink-0 px-3 py-1.5 ${chatOpen ? "btn-secondary" : "btn-primary"}`}
        >
          {chatOpen ? (
            "Close chat"
          ) : (
            // One flex item, so the button's gap doesn't widen the space; phones show "Ask".
            <span>
              Ask<span className="max-sm:hidden"> a question</span>
            </span>
          )}
        </button>
      </div>

      {notice && (
        <div
          role={notice.error ? "alert" : "status"}
          className={`animate-fade-in flex items-center gap-3 border-b px-4 py-2 text-sm ${
            notice.error
              ? "border-rose-200/70 bg-rose-50 text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-200"
              : "border-slate-900/[0.06] bg-slate-900/[0.03] text-slate-700 dark:border-white/[0.06] dark:bg-white/[0.04] dark:text-slate-200"
          }`}
        >
          <span className="flex-1">{notice.text}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            aria-label="Dismiss"
            className="btn btn-ghost h-7 w-7 p-0"
          >
            ✕
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {showTree && (
          <aside
            aria-label="File tree"
            className="animate-fade-in w-72 shrink-0 overflow-auto border-r border-slate-900/[0.06] bg-slate-50 max-lg:absolute max-lg:top-12 max-lg:bottom-0 max-lg:left-0 max-lg:z-10 max-lg:shadow-xl dark:border-white/[0.06] dark:bg-black"
          >
            {tree.isPending && <LoadingState label="Loading files" />}
            {tree.isError && (
              <div className="p-3">
                <ErrorState message={tree.error.message} onRetry={() => tree.refetch()} />
              </div>
            )}
            {tree.data && (
              <FileTree
                files={tree.data.files}
                selectedPath={filePath}
                onSelect={(path) => {
                  openFile(path);
                  if (!isWide()) setShowTree(false);
                }}
              />
            )}
          </aside>
        )}

        <main className="flex min-w-0 flex-1 flex-col">
          {filePath ? (
            <CodeViewer
              repoId={repoId}
              path={filePath}
              range={range}
              onClose={() => update({ file: null, lines: null })}
              onRangeChange={(next) => openFile(filePath, next)}
            />
          ) : (
            <>
              <TabBar active={tab} onSelect={(key) => update({ tab: key })} />
              <div
                key={tab}
                role="tabpanel"
                className="animate-fade-up min-h-0 flex-1 overflow-auto"
              >
                {tab === "overview" && (
                  <>
                    <SectionShell
                      title="Overview"
                      section={analysis.data?.sections.overview}
                      {...sectionProps}
                    >
                      {(data) => <OverviewSection data={data} onOpen={openRef} onAsk={askInChat} />}
                    </SectionShell>
                    <IndexSummary repo={repo.data} />
                  </>
                )}
                {tab === "start-here" && (
                  <SectionShell
                    title="Start Here"
                    section={analysis.data?.sections.start_here}
                    {...sectionProps}
                  >
                    {(data) => <StartHereSection data={data} onOpen={openRef} />}
                  </SectionShell>
                )}
                {tab === "glossary" && (
                  <SectionShell
                    title="Glossary"
                    section={analysis.data?.sections.glossary}
                    {...sectionProps}
                  >
                    {(data) => <GlossarySection data={data} onOpen={openRef} />}
                  </SectionShell>
                )}
                {tab === "architecture" && (
                  <SectionShell
                    title="Architecture"
                    section={analysis.data?.sections.architecture}
                    {...sectionProps}
                  >
                    {(data) => <ArchitectureSection data={data} onOpen={openRef} />}
                  </SectionShell>
                )}
                {tab === "tour" && (
                  <SectionShell
                    title="Guided Tour"
                    section={analysis.data?.sections.tour}
                    {...sectionProps}
                  >
                    {(data) => <TourSection repoId={repoId} data={data} onOpen={openRef} />}
                  </SectionShell>
                )}
              </div>
            </>
          )}
        </main>

        {chatOpen && (
          <aside
            aria-label="Chat"
            className="animate-slide-in-right flex w-96 shrink-0 flex-col border-l border-slate-900/[0.06] max-lg:absolute max-lg:top-12 max-lg:bottom-0 max-lg:right-0 max-lg:z-10 max-lg:w-full max-lg:max-w-md max-lg:bg-white/85 max-lg:shadow-2xl max-lg:backdrop-blur-xl dark:border-white/[0.06] max-lg:dark:bg-black/80"
          >
            <div className="border-b border-slate-900/[0.06] px-4 py-3 text-sm font-semibold dark:border-white/[0.06]">
              Ask about this codebase
            </div>
            <div className="min-h-0 flex-1">
              <ChatPanel
                key={chatRequest?.nonce ?? "chat"}
                repoId={repoId}
                starterQuestions={analysis.data?.sections.overview.data?.starter_questions ?? []}
                onOpen={openRef}
                autoAsk={chatRequest?.text}
              />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
