import { NavLink, Outlet, useLocation } from "react-router";

import { LiveBackground } from "./LiveBackground";
import { ModelBanner } from "./ModelBanner";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors duration-300 ${
    isActive
      ? "bg-slate-900/[0.06] text-slate-900 dark:bg-white/10 dark:text-white"
      : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
  }`;

export function Layout() {
  const { pathname } = useLocation();
  // The workspace and tour mode use the full width; align the header with them.
  const wide = pathname.startsWith("/repos/");
  return (
    <div className="flex h-dvh flex-col">
      <LiveBackground />
      <ModelBanner />
      <header className="z-20 shrink-0 border-b border-slate-900/[0.06] bg-slate-50/80 backdrop-blur-md dark:border-white/[0.06] dark:bg-black/70">
        <div
          className={`mx-auto flex h-14 items-center gap-2 px-3 sm:gap-4 sm:px-4 ${wide ? "" : "max-w-7xl"}`}
        >
          <NavLink to="/" className="group flex items-center gap-2.5 font-semibold tracking-tight">
            <span className="bg-brand flex h-7 w-7 items-center justify-center rounded-lg text-sm font-bold transition-transform duration-450 group-hover:-rotate-6">
              R
            </span>
            <span className="max-sm:hidden">RepoGuide</span>
          </NavLink>
          <nav className="flex items-center gap-1" aria-label="Main">
            <NavLink to="/dashboard" className={navClass}>
              Dashboard
            </NavLink>
            <NavLink to="/settings" className={navClass}>
              Settings
            </NavLink>
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">
        {/* Re-keyed per page: each page fades up when you navigate to it. */}
        <div key={pathname} className="animate-page-in h-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
