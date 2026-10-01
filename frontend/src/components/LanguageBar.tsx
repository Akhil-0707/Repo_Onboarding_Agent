import { languageColor } from "../lib/languages";

export function LanguageBar({
  languages,
  limit = 5,
}: {
  languages: Record<string, number>;
  limit?: number;
}) {
  const entries = Object.entries(languages).slice(0, limit);
  if (!entries.length) return null;
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        {entries.map(([language, pct]) => (
          <span
            key={language}
            style={{ width: `${pct}%`, backgroundColor: languageColor(language) }}
            title={`${language} ${pct}%`}
          />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
        {entries.map(([language, pct]) => (
          <li key={language} className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: languageColor(language) }}
            />
            {language} <span className="text-slate-400">{pct}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
