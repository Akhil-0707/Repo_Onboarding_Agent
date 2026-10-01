import { Link } from "react-router";

import { EmptyState } from "../components/StateViews";

export function DashboardPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-2xl font-bold">Your repositories</h1>
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
