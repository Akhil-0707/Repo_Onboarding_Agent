/**
 * Syntax highlighting with Shiki (JS regex engine, no WASM). Grammars load lazily per language,
 * and we render tokens ourselves so line ranges can be highlighted precisely.
 */
import type { HighlighterCore, LanguageRegistration } from "shiki/core";

export interface Token {
  content: string;
  color?: string;
  darkColor?: string;
}

type LangModule = { default: LanguageRegistration[] };

const LANGS: Record<string, () => Promise<LangModule>> = {
  python: () => import("shiki/langs/python.mjs"),
  javascript: () => import("shiki/langs/javascript.mjs"),
  typescript: () => import("shiki/langs/typescript.mjs"),
  tsx: () => import("shiki/langs/tsx.mjs"),
  java: () => import("shiki/langs/java.mjs"),
  go: () => import("shiki/langs/go.mjs"),
  ruby: () => import("shiki/langs/ruby.mjs"),
  rust: () => import("shiki/langs/rust.mjs"),
  c: () => import("shiki/langs/c.mjs"),
  cpp: () => import("shiki/langs/cpp.mjs"),
  csharp: () => import("shiki/langs/csharp.mjs"),
  php: () => import("shiki/langs/php.mjs"),
  kotlin: () => import("shiki/langs/kotlin.mjs"),
  swift: () => import("shiki/langs/swift.mjs"),
  scala: () => import("shiki/langs/scala.mjs"),
  shell: () => import("shiki/langs/shellscript.mjs"),
  powershell: () => import("shiki/langs/powershell.mjs"),
  sql: () => import("shiki/langs/sql.mjs"),
  html: () => import("shiki/langs/html.mjs"),
  css: () => import("shiki/langs/css.mjs"),
  scss: () => import("shiki/langs/scss.mjs"),
  less: () => import("shiki/langs/less.mjs"),
  vue: () => import("shiki/langs/vue.mjs"),
  svelte: () => import("shiki/langs/svelte.mjs"),
  markdown: () => import("shiki/langs/markdown.mjs"),
  json: () => import("shiki/langs/json.mjs"),
  yaml: () => import("shiki/langs/yaml.mjs"),
  toml: () => import("shiki/langs/toml.mjs"),
  ini: () => import("shiki/langs/ini.mjs"),
  xml: () => import("shiki/langs/xml.mjs"),
  groovy: () => import("shiki/langs/groovy.mjs"),
  protobuf: () => import("shiki/langs/proto.mjs"),
  graphql: () => import("shiki/langs/graphql.mjs"),
  hcl: () => import("shiki/langs/hcl.mjs"),
  lua: () => import("shiki/langs/lua.mjs"),
  dart: () => import("shiki/langs/dart.mjs"),
  elixir: () => import("shiki/langs/elixir.mjs"),
  r: () => import("shiki/langs/r.mjs"),
  julia: () => import("shiki/langs/julia.mjs"),
  dockerfile: () => import("shiki/langs/dockerfile.mjs"),
  makefile: () => import("shiki/langs/make.mjs"),
};

/** Our language ids that differ from Shiki's grammar names. */
const SHIKI_IDS: Record<string, string> = {
  shell: "shellscript",
  makefile: "make",
  protobuf: "proto",
};

/** Above these sizes we show plain text: highlighting would make the viewer sluggish. */
export const MAX_HIGHLIGHT_LINES = 4000;
export const MAX_HIGHLIGHT_CHARS = 250_000;

let highlighterPromise: Promise<HighlighterCore> | null = null;
const loaded = new Set<string>();

function getHighlighter(): Promise<HighlighterCore> {
  if (!highlighterPromise) {
    highlighterPromise = (async () => {
      const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] = await Promise.all([
        import("shiki/core"),
        import("shiki/engine/javascript"),
      ]);
      return createHighlighterCore({
        themes: [import("shiki/themes/github-light.mjs"), import("shiki/themes/github-dark.mjs")],
        langs: [],
        engine: createJavaScriptRegexEngine({ forgiving: true }),
      });
    })();
  }
  return highlighterPromise;
}

export function canHighlight(language: string, code: string): boolean {
  return (
    language in LANGS &&
    code.length <= MAX_HIGHLIGHT_CHARS &&
    code.split("\n").length <= MAX_HIGHLIGHT_LINES
  );
}

export function plainTokens(code: string): Token[][] {
  return code.split("\n").map((line) => [{ content: line }]);
}

export async function highlight(code: string, language: string): Promise<Token[][]> {
  if (!canHighlight(language, code)) return plainTokens(code);
  const highlighter = await getHighlighter();
  if (!loaded.has(language)) {
    const loader = LANGS[language];
    if (!loader) return plainTokens(code);
    await highlighter.loadLanguage((await loader()).default);
    loaded.add(language);
  }
  const result = highlighter.codeToTokens(code, {
    lang: SHIKI_IDS[language] ?? language,
    themes: { light: "github-light", dark: "github-dark" },
  });
  return result.tokens.map((line) =>
    line.map((token) => {
      const style = (token.htmlStyle ?? {}) as Record<string, string>;
      return { content: token.content, color: style.color, darkColor: style["--shiki-dark"] };
    }),
  );
}
