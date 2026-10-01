import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useAuth } from "../lib/auth";
import { LoadingState } from "./StateViews";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <LoadingState label="Checking your session" />;
  if (status === "anonymous") {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}
