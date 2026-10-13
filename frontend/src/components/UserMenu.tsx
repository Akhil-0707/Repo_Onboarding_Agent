import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useAuth } from "../lib/auth";

export function UserMenu() {
  const { status, user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (status === "loading") return null;
  if (!user) {
    return (
      <Link to="/login" className="btn btn-primary px-3 py-1.5">
        Sign in
      </Link>
    );
  }

  return (
    <div className="relative" ref={root}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full p-0.5 ring-slate-900/10 transition-shadow duration-300 hover:ring-4 dark:ring-white/15"
      >
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="h-8 w-8 rounded-full" />
        ) : (
          <span className="bg-brand flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
        )}
        <span className="sr-only">Account menu for {user.username}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="animate-pop-in absolute right-0 z-30 mt-2 w-52 origin-top-right rounded-xl bg-white p-1 shadow-xl ring-1 shadow-slate-900/10 ring-slate-900/[0.08] dark:bg-neutral-900 dark:shadow-black/60 dark:ring-white/10"
        >
          <p className="truncate px-3 py-2 text-xs text-slate-500">@{user.username}</p>
          <Link
            role="menuitem"
            to="/settings"
            onClick={() => setOpen(false)}
            className="block rounded-lg px-3 py-2 text-sm transition-colors duration-200 hover:bg-slate-900/5 dark:hover:bg-white/10"
          >
            Settings
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={async () => {
              setOpen(false);
              await logout();
              navigate("/");
            }}
            className="block w-full rounded-lg px-3 py-2 text-left text-sm transition-colors duration-200 hover:bg-slate-900/5 dark:hover:bg-white/10"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
