import { Link } from "react-router";

import { formatCost, useUserUsage } from "../api/usage";
import type { UsageTotals } from "../api/usage";
import { ErrorState, LoadingState } from "./StateViews";

const number = new Intl.NumberFormat();

function tokens(usage: UsageTotals | null | undefined): string {
  return usage ? number.format(usage.total_tokens) : "—";
}

function seconds(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${ms} ms`;
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
      {hint && <dd className="text-xs text-slate-500">{hint}</dd>}
    </div>
  );
}

/** Tokens and latency are the primary metrics; the dollar estimate is secondary. */
export function UsageSummary() {
  const usage = useUserUsage();
  if (usage.isPending) return <LoadingState label="Loading usage" />;
  if (usage.isError) {
    return <ErrorState message={usage.error.message} onRetry={() => usage.refetch()} />;
  }
  const { totals, repositories, rate_limit, pricing } = usage.data;
  const quota = rate_limit.new_analyses;
  const resetMinutes = Math.ceil(quota.reset_in_seconds / 60);

  return (
    <div className="mt-3 flex flex-col gap-5 text-sm">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric
          label="Analysis tokens"
          value={number.format(totals.analysis.total_tokens)}
          hint={`${totals.analysis.calls} model calls`}
        />
        <Metric
          label="Chat tokens"
          value={number.format(totals.chat.total_tokens)}
          hint={`${totals.chat.questions} questions`}
        />
        <Metric label="Model time" value={seconds(totals.all.latency_ms)} />
        <Metric label="Estimated cost" value={formatCost(totals.all.est_cost, pricing)} />
      </dl>

      <p>
        <span className="font-medium">New analyses:</span> {quota.remaining} of {quota.limit} left
        this hour
        {quota.remaining === 0 && resetMinutes > 0 && ` (next one in ${resetMinutes} min)`}.{" "}
        <span className="text-slate-500">
          Repositories someone already analysed open instantly and do not count.
        </span>
      </p>

      {repositories.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <caption className="sr-only">Usage per repository</caption>
            <thead className="text-xs text-slate-500">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Repository
                </th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">
                  Analysis
                </th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">
                  Chat
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  Questions
                </th>
              </tr>
            </thead>
            <tbody>
              {repositories.map((repo) => (
                <tr key={repo.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-3">
                    {repo.on_dashboard ? (
                      <Link to={`/repos/${repo.id}`} className="font-mono hover:underline">
                        {repo.full_name}
                      </Link>
                    ) : (
                      <span className="font-mono">{repo.full_name}</span>
                    )}
                    <span className="ml-1 font-mono text-xs text-slate-500">
                      @{repo.commit_sha.slice(0, 7)}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">
                    {repo.started_by_you ? tokens(repo.analysis) : "cached (free)"}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{tokens(repo.chat)}</td>
                  <td className="py-1.5 text-right tabular-nums">{repo.chat?.questions ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
