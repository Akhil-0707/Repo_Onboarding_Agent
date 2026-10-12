import { useLLMHealth } from "../api/health";

/** Shown app-wide whenever the self-hosted model server (Kaggle) is unreachable. */
export function ModelBanner() {
  const { data, isError } = useLLMHealth();

  if (isError) {
    return (
      <div
        role="status"
        className="animate-fade-in border-b border-rose-500/20 bg-rose-500/10 px-4 py-2 text-center text-sm text-rose-700 dark:text-rose-300"
      >
        Cannot reach the RepoGuide server. Retrying automatically…
      </div>
    );
  }
  if (!data || data.online) return null;

  return (
    <div
      role="status"
      className="animate-fade-in border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-800 dark:text-amber-200"
    >
      The AI model is offline. Analyses will wait and resume automatically, and chat is paused until
      it is back.
    </div>
  );
}
