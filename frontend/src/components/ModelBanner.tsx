import { useLLMHealth } from "../api/health";

/** Shown app-wide whenever the self-hosted model server (Kaggle) is unreachable. */
export function ModelBanner() {
  const { data, isError } = useLLMHealth();

  if (isError) {
    return (
      <div role="status" className="bg-rose-600 px-4 py-2 text-center text-sm text-white">
        Cannot reach the RepoGuide server. Retrying automatically…
      </div>
    );
  }
  if (!data || data.online) return null;

  return (
    <div
      role="status"
      className="bg-amber-500 px-4 py-2 text-center text-sm font-medium text-amber-950"
    >
      The AI model is offline. Analyses will wait and resume automatically, and chat is paused until
      it is back.
    </div>
  );
}
