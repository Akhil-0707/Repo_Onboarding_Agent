import { Link } from "react-router";

import { EmptyState } from "../components/StateViews";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        title="Page not found"
        description="The page you are looking for does not exist."
        action={
          <Link to="/" className="text-indigo-600 hover:underline dark:text-indigo-400">
            Go home
          </Link>
        }
      />
    </div>
  );
}
