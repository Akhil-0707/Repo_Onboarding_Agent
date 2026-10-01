import { useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router";

import { useAnalysis } from "../api/analysis";
import { useRepository, useTree } from "../api/repos";
import type { Repository } from "../api/types";
import { CodeViewer } from "../components/CodeViewer";
import type { LineRange } from "../components/CodeViewer";
import { FileTree } from "../components/FileTree";
import { LanguageBar } from "../components/LanguageBar";
import { GlossarySection } from "../components/sections/GlossarySection";
import { OverviewSection } from "../components/sections/OverviewSection";
import { SectionShell } from "../components/sections/SectionShell";
import { StartHereSection } from "../components/sections/StartHereSection";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
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

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-lg font-semibold">{value?.toLocaleString() ?? "—"}</dd>
    </div>
  );
}

function IndexSummary({ repo }: { repo: Repository }) {
  const scripts = Object.entries(repo.detection.scripts ?? {}).slice(0, 8);
  return (
    <div className="flex flex-col gap-6 border-t border-slate-200 p-6 dark:border-slate-800">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Repository facts
      </h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Files" value={repo.stats.files} />
        <Stat label="Lines" value={repo.stats.lines} />
        <Stat label="Symbols" value={repo.stats.symbols} />
        <Stat label="Internal imports" value={repo.stats.dependency_edges} />
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
                className="rounded-full bg-slate-100 px-2.5 py-0.5 text-sm dark:bg-slate-800"
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
                <span className="text-indigo-600 dark:text-indigo-400">{name}</span>
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
  const [showTree, setShowTree] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);

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
      <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
        <button
          type="button"
          onClick={() => setShowTree((value) => !value)}
          aria-pressed={showTree}
          className="rounded px-2 py-1 text-sm hover:bg-slate-200 dark:hover:bg-slate-800"
        >
          {showTree ? "Hide files" : "Files"}
        </button>
        <Link to="/dashboard" className="text-sm text-slate-500 hover:underline">
          Dashboard
        </Link>
        <span className="text-slate-300">/</span>
        <h1 className="truncate font-mono text-sm font-semibold">{repo.data.full_name}</h1>
        <a
          href={`${repo.data.url}/tree/${repo.data.commit_sha}`}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-xs text-slate-500 hover:underline"
        >
          @{repo.data.commit_sha.slice(0, 7)}
        </a>
        {analysis.data && analysis.data.status !== "done" && (
          <StatusBadge status={analysis.data.status} />
        )}
        <button
          type="button"
          onClick={() => setChatOpen((value) => !value)}
          aria-pressed={chatOpen}
          className="ml-auto rounded-md border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {chatOpen ? "Close chat" : "Ask a question"}
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        {showTree && (
          <aside
            aria-label="File tree"
            className="w-72 shrink-0 border-r border-slate-200 bg-slate-50 max-lg:absolute max-lg:top-10 max-lg:bottom-0 max-lg:left-0 max-lg:z-10 max-lg:shadow-xl dark:border-slate-800 dark:bg-slate-950"
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
                onSelect={(path) => openFile(path)}
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
              <nav
                role="tablist"
                aria-label="Onboarding sections"
                className="flex gap-1 overflow-x-auto border-b border-slate-200 px-4 dark:border-slate-800"
              >
                {TABS.map((item) => (
                  <button
                    key={item.key}
                    role="tab"
                    type="button"
                    aria-selected={tab === item.key}
                    onClick={() => update({ tab: item.key })}
                    className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap ${
                      tab === item.key
                        ? "border-indigo-600 text-indigo-700 dark:text-indigo-300"
                        : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </nav>
              <div role="tabpanel" className="min-h-0 flex-1 overflow-auto">
                {tab === "overview" && (
                  <>
                    <SectionShell
                      title="Overview"
                      section={analysis.data?.sections.overview}
                      analysisStatus={analysis.data?.status}
                    >
                      {(data) => <OverviewSection data={data} onOpen={openRef} />}
                    </SectionShell>
                    <IndexSummary repo={repo.data} />
                  </>
                )}
                {tab === "start-here" && (
                  <SectionShell
                    title="Start Here"
                    section={analysis.data?.sections.start_here}
                    analysisStatus={analysis.data?.status}
                  >
                    {(data) => <StartHereSection data={data} onOpen={openRef} />}
                  </SectionShell>
                )}
                {tab === "glossary" && (
                  <SectionShell
                    title="Glossary"
                    section={analysis.data?.sections.glossary}
                    analysisStatus={analysis.data?.status}
                  >
                    {(data) => <GlossarySection data={data} onOpen={openRef} />}
                  </SectionShell>
                )}
                {(tab === "architecture" || tab === "tour") && (
                  <div className="p-6">
                    <EmptyState
                      title="Not generated yet"
                      description="This section is not part of the analysis yet."
                    />
                  </div>
                )}
              </div>
            </>
          )}
        </main>

        {chatOpen && (
          <aside
            aria-label="Chat"
            className="flex w-96 shrink-0 flex-col border-l border-slate-200 bg-white max-lg:absolute max-lg:top-10 max-lg:bottom-0 max-lg:right-0 max-lg:z-10 max-lg:w-full max-lg:max-w-md max-lg:shadow-xl dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="border-b border-slate-200 px-4 py-2 font-semibold dark:border-slate-800">
              Ask about this codebase
            </div>
            <div className="flex-1 p-4">
              <EmptyState
                title="Chat is not available yet"
                description="Questions are answered by the AI model once this repository has been analyzed."
              />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
