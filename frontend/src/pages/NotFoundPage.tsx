import { Link } from "react-router";

import { EmptyState } from "../components/StateViews";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        title="Page not found"
        description="The page you are looking for does not exist."
        action={
          <Link
            to="/"
            className="text-slate-900 underline decoration-slate-300 underline-offset-4 transition-colors duration-200 hover:decoration-slate-900 dark:text-white dark:decoration-slate-600 dark:hover:decoration-white"
          >
            Go home
          </Link>
        }
      />
    </div>
  );
}
