import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import type { User } from "../api/auth";
import { setAccessTokenProvider, setUnauthorizedHandler } from "../api/client";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  user: User | null;
  /** Complete sign-in with the one-time code from the OAuth callback. */
  completeLogin: (code: string) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Session model: the access token lives only in memory (never localStorage); the refresh token
 * is an httpOnly cookie. On load and on any 401 we refresh silently, single-flight.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const tokenRef = useRef<string | null>(null);
  const refreshInFlight = useRef<Promise<string | null> | null>(null);

  const applySession = useCallback((session: authApi.SessionResponse | null) => {
    tokenRef.current = session?.access ?? null;
    setUser(session?.user ?? null);
    setStatus(session ? "authenticated" : "anonymous");
  }, []);

  const refresh = useCallback((): Promise<string | null> => {
    if (!refreshInFlight.current) {
      refreshInFlight.current = authApi
        .refreshSession()
        .then((session) => {
          applySession(session);
          return session.access;
        })
        .catch(() => {
          applySession(null);
          return null;
        })
        .finally(() => {
          refreshInFlight.current = null;
        });
    }
    return refreshInFlight.current;
  }, [applySession]);

  useEffect(() => {
    setAccessTokenProvider(() => tokenRef.current);
    setUnauthorizedHandler(refresh);
    void refresh();
    return () => {
      setAccessTokenProvider(() => null);
      setUnauthorizedHandler(null);
    };
  }, [refresh]);

  const completeLogin = useCallback(
    async (code: string) => {
      const session = await authApi.exchangeCode(code);
      applySession(session);
      return session.user;
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      applySession(null);
      queryClient.clear();
    }
  }, [applySession, queryClient]);

  const value = useMemo(
    () => ({ status, user, completeLogin, logout }),
    [status, user, completeLogin, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
