const COLORS: Record<string, string> = {
  python: "#3572A5",
  javascript: "#f1e05a",
  typescript: "#3178c6",
  tsx: "#3178c6",
  java: "#b07219",
  go: "#00ADD8",
  ruby: "#701516",
  rust: "#dea584",
  c: "#555555",
  cpp: "#f34b7d",
  csharp: "#178600",
  php: "#4F5D95",
  kotlin: "#A97BFF",
  swift: "#F05138",
  shell: "#89e051",
  html: "#e34c26",
  css: "#563d7c",
  scss: "#c6538c",
  vue: "#41b883",
  dockerfile: "#384d54",
  makefile: "#427819",
};

export function languageColor(language: string): string {
  return COLORS[language] ?? "#94a3b8";
}
