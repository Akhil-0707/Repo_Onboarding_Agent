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
    <div className="mx-auto flex max-w-3xl flex-col items-center px-4 py-24 text-center">
      <h1 className="animate-fade-up text-4xl font-semibold tracking-tight sm:text-6xl">
        Understand any codebase <span className="text-brand">in minutes</span>
      </h1>
      <p className="animate-fade-up mt-5 max-w-xl text-lg text-slate-600 [animation-delay:80ms] dark:text-slate-400">
        Paste a GitHub repository. RepoGuide maps its architecture, picks the files to read first,
        walks you through the code, and answers questions with citations.
      </p>

      <form
        onSubmit={submit}
        className="animate-fade-up mt-10 flex w-full flex-col gap-3 [animation-delay:160ms] sm:flex-row"
        noValidate
      >
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
          className="field flex-1 px-4 py-3 text-base"
        />
        <button type="submit" className="btn btn-primary px-6 py-3 text-base">
          Analyze
        </button>
      </form>
      {error && (
        <p
          id="repo-url-error"
          role="alert"
          className="animate-fade-in mt-2 text-sm text-rose-600 dark:text-rose-400"
        >
          {error}
        </p>
      )}

      <section
        className="animate-fade-up mt-16 w-full text-left [animation-delay:240ms]"
        aria-labelledby="examples-heading"
      >
        <h2 id="examples-heading" className="eyebrow">
          Try an example
        </h2>
        <ul className="stagger mt-4 grid gap-3 sm:grid-cols-2">
          {EXAMPLE_REPOS.map((example) => (
            <li key={example.slug}>
              <button
                type="button"
                onClick={() => setValue(`https://github.com/${example.slug}`)}
                className="surface surface-hover w-full p-4 text-left"
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
