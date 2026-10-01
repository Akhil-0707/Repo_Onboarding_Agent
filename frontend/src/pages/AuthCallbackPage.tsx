import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { ErrorState, LoadingState } from "../components/StateViews";
import { useAuth } from "../lib/auth";
import { safeNext } from "../lib/navigation";

/** Landing spot after GitHub: trades the one-time code for a session, then moves on. */
export function AuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const [error, setError] = useState<string | null>(params.get("error"));
  // The code is single-use; StrictMode runs effects twice in development.
  const started = useRef(false);

  useEffect(() => {
    const code = params.get("code");
    if (started.current || !code || params.get("error")) return;
    started.current = true;
    completeLogin(code)
      .then(() => navigate(safeNext(params.get("next")), { replace: true }))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Sign-in failed. Please try again."),
      );
  }, [params, completeLogin, navigate]);

  if (!params.get("code") && !error) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <ErrorState title="Nothing to do here" message="This page is only used during sign-in." />
      </div>
    );
  }
  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <ErrorState title="Sign-in failed" message={error} />
        <Link to="/login" className="mt-4 inline-block text-indigo-600 hover:underline">
          Try again
        </Link>
      </div>
    );
  }
  return <LoadingState label="Signing you in…" />;
}
