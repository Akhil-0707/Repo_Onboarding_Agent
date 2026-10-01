import { useLLMHealth } from "../api/health";
import { ErrorState, LoadingState } from "../components/StateViews";

export function SettingsPage() {
  const health = useLLMHealth();

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="font-semibold">Model server</h2>
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
