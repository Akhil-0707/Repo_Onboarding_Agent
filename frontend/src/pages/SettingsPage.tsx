import { githubLoginUrl } from "../api/auth";
import { useLLMHealth } from "../api/health";
import { ErrorState, LoadingState } from "../components/StateViews";
import { useAuth } from "../lib/auth";

const card =
  "mt-6 rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900";

export function SettingsPage() {
  const health = useLLMHealth();
  const { user } = useAuth();

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      <section className={card} aria-labelledby="github-heading">
        <h2 id="github-heading" className="font-semibold">
          GitHub connection
        </h2>
        {user && (
          <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-slate-500">Account</dt>
            <dd>@{user.username}</dd>
            <dt className="text-slate-500">Status</dt>
            <dd className={user.github_connected ? "text-emerald-600" : "text-amber-600"}>
              {user.github_connected ? "Connected" : "Not connected"}
            </dd>
            <dt className="text-slate-500">Private repositories</dt>
            <dd>
              {user.private_repo_access ? (
                "Allowed"
              ) : (
                <a
                  href={githubLoginUrl({ next: "/settings", privateRepos: true })}
                  className="text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  Grant access
                </a>
              )}
            </dd>
          </dl>
        )}
      </section>

      <section className={card} aria-labelledby="model-heading">
        <h2 id="model-heading" className="font-semibold">
          Model server
        </h2>
        {health.isPending && <LoadingState label="Checking model server" />}
        {health.isError && (
          <ErrorState
            message="Could not check the model server."
            onRetry={() => health.refetch()}
          />
        )}
        {health.data && (
          <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-slate-500">Status</dt>
            <dd className={health.data.online ? "text-emerald-600" : "text-amber-600"}>
              {health.data.online ? "Online" : "Offline"}
            </dd>
            <dt className="text-slate-500">Model</dt>
            <dd className="font-mono">{health.data.model}</dd>
            <dt className="text-slate-500">Latency</dt>
            <dd>{health.data.latency_ms != null ? `${health.data.latency_ms} ms` : "—"}</dd>
          </dl>
        )}
      </section>
    </div>
  );
}
