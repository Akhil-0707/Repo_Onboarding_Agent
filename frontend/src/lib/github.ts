export interface RepoRef {
  owner: string;
  name: string;
}

const NAME = /^[A-Za-z0-9_.-]{1,100}$/;

/** Accepts `https://github.com/owner/repo(.git)(/...)`, `github.com/owner/repo` or `owner/repo`. */
export function parseGitHubUrl(input: string): RepoRef | null {
  let value = input.trim();
  if (!value) return null;
  if (/^[\w.-]+\/[\w.-]+$/.test(value)) value = `https://github.com/${value}`;
  if (!/^https?:\/\//i.test(value)) value = `https://${value}`;

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (!["github.com", "www.github.com"].includes(url.hostname.toLowerCase())) return null;

  const [owner, rawName] = url.pathname.split("/").filter(Boolean);
  if (!owner || !rawName) return null;
  const name = rawName.replace(/\.git$/i, "");
  if (!NAME.test(owner) || !NAME.test(name) || name === "." || name === "..") return null;
  return { owner, name };
}

export function githubBlobUrl(
  repo: RepoRef,
  commitSha: string,
  path: string,
  start?: number,
  end?: number,
): string {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  const anchor = start ? (end && end !== start ? `#L${start}-L${end}` : `#L${start}`) : "";
  return `https://github.com/${repo.owner}/${repo.name}/blob/${commitSha}/${encodedPath}${anchor}`;
}

/** Point a GitHub file URL at a line range (``#L5`` or ``#L5-L9``). */
export function githubRangeLink(
  fileUrl: string,
  range: { start: number; end: number } | null,
): string {
  const base = fileUrl.split("#")[0] ?? fileUrl;
  if (!range) return base;
  return range.start === range.end
    ? `${base}#L${range.start}`
    : `${base}#L${range.start}-L${range.end}`;
}
