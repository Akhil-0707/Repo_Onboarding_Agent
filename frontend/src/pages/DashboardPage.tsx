import { Link, useSearchParams } from "react-router";

import { EmptyState } from "../components/StateViews";
import { useAuth } from "../lib/auth";

export function DashboardPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const pending = params.get("analyze");

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Your repositories</h1>
          {user && (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Signed in as @{user.username}
            </p>
          )}
        </div>
        <Link
          to="/"
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          New analysis
        </Link>
      </div>

      {pending && (
        <div
          role="status"
          className="mt-6 rounded-lg border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200"
        >
          Ready to analyze <span className="font-mono font-semibold">{pending}</span>.
        </div>
      )}

      <div className="mt-6">
        <EmptyState
          title="No repositories yet"
          description="Analyze a GitHub repository to get an overview, architecture map, guided tour and Q&A."
          action={
            <Link
              to="/"
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              Analyze a repository
            </Link>
          }
        />
      </div>
    </div>
  );
}
