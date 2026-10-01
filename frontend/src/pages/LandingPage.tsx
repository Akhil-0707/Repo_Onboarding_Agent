import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";

import { EXAMPLE_REPOS } from "../lib/examples";
import { parseGitHubUrl } from "../lib/github";

export function LandingPage() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const repo = parseGitHubUrl(value);
    if (!repo) {
      setError("Enter a GitHub repository URL like https://github.com/owner/repo");
      return;
    }
    setError(null);
    navigate(`/dashboard?analyze=${encodeURIComponent(`${repo.owner}/${repo.name}`)}`);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center px-4 py-20 text-center">
      <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
        Understand any codebase{" "}
        <span className="text-indigo-600 dark:text-indigo-400">in minutes</span>
      </h1>
      <p className="mt-4 max-w-xl text-lg text-slate-600 dark:text-slate-400">
        Paste a GitHub repository. RepoGuide maps its architecture, picks the files to read first,
        walks you through the code, and answers questions with citations.
      </p>

      <form onSubmit={submit} className="mt-10 flex w-full flex-col gap-3 sm:flex-row" noValidate>
        <label htmlFor="repo-url" className="sr-only">
          GitHub repository URL
        </label>
        <input
          id="repo-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          placeholder="https://github.com/owner/repo"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "repo-url-error" : undefined}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-base shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          className="rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white shadow-sm hover:bg-indigo-700"
        >
          Analyze
        </button>
      </form>
      {error && (
        <p
          id="repo-url-error"
          role="alert"
          className="mt-2 text-sm text-rose-600 dark:text-rose-400"
        >
          {error}
        </p>
      )}

      <section className="mt-14 w-full text-left" aria-labelledby="examples-heading">
        <h2
          id="examples-heading"
          className="text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Try an example
        </h2>
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {EXAMPLE_REPOS.map((example) => (
            <li key={example.slug}>
              <button
                type="button"
                onClick={() => setValue(`https://github.com/${example.slug}`)}
                className="w-full rounded-lg border border-slate-200 bg-white p-4 text-left hover:border-indigo-400 dark:border-slate-800 dark:bg-slate-900"
              >
                <span className="font-mono text-sm font-semibold">{example.slug}</span>
                <span className="mt-1 block text-sm text-slate-500 dark:text-slate-400">
                  {example.blurb}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
